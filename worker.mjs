// Private stdin/stdout channel of this N.E.K.O. plugin instance.
import {createInterface} from 'node:readline';
import {DatabaseSync} from 'node:sqlite';
import {join, resolve} from 'node:path';
import {AsyncLocalStorage} from 'node:async_hooks';
import {createHash} from 'node:crypto';
import {loadSettings, lock, makeWorld, pinServer, clientVersions} from './runtime/src/local.mjs';
import {STARPOST_TOOL_DECLS} from './runtime/lib/core.mjs';

const dir=resolve(process.argv[2]);
const toolViews=new AsyncLocalStorage();
let db, world, unlock, tool, started=false;
function frame(e) {
  return {origin:e.origin,type:e.type,time:e.ts,senderKey:e.senderKey,text:e.text,
    images:(e.blobs||[]).map(b=>({mime:b.mime,data:Buffer.from(b.bytes).toString('base64')}))};
}
function promote() {
  const row=db.prepare("SELECT max(id) AS id FROM delivery WHERE mode='pending'").get();
  if(row.id===null) return false;
  db.prepare("UPDATE delivery SET mode=CASE WHEN id=? THEN 'respond' ELSE 'read' END WHERE mode='pending'").run(row.id);
  return true;
}
const host={
  modelFacts:{accepts:mime=>/^image\/(png|jpeg|webp|gif)$/.test(mime)},
  async pushEvent(event,delivery={}) {
    const item=frame(event), views=toolViews.getStore();
    if(views){views.push(item);return {cursor:0};}
    const mode=delivery.trigger==='piggyback'?'pending':'respond';
    const body=JSON.stringify(item);
    const key=createHash('sha256').update(body).digest('hex');
    db.exec('BEGIN');
    try {
      if(event.senderKey==='starpost.owner' && mode==='respond')
        db.prepare("UPDATE delivery SET mode='read' WHERE mode='pending'").run();
      db.prepare('INSERT OR IGNORE INTO delivery(event_key,origin,body,mode) VALUES(?,?,?,?)').run(key,event.origin,body,mode);
      const row=db.prepare('SELECT id FROM delivery WHERE event_key=?').get(key);
      db.exec('COMMIT');
      return {cursor:row.id};
    } catch(error){db.exec('ROLLBACK');throw error;}
  },
  async promotePending(){return promote();},
  async drainPendingEvents(predicate){
    for(const origin of ['external','internal']) if(predicate({source:'starpost',origin}))
      db.prepare('DELETE FROM delivery WHERE origin=?').run(origin);
  }
};
async function request(op,args) {
  if(op==='init') {
    if(unlock) throw Error('星邮运行端已经初始化');
    unlock=lock(dir);
    const saved=loadSettings(dir), character=saved.sessionId;
    if(typeof character!=='string'||!character.trim()) throw Error('请先停用插件，并通过 account.mjs hub-login --character 角色名完成配对。');
    world=makeWorld(dir,{...saved,...args});
    const status=await world.webUi().invoke('viewer','status',[]);
    if(!status.registered) throw Error('请先完成人类账号配对，再启动插件。');
    pinServer(dir,saved);
    const roleKey=createHash('sha256').update(character).digest('hex').slice(0,24);
    db=new DatabaseSync(join(dir,'neko-delivery-'+status.botId+'-'+roleKey+'.sqlite'));
    db.exec('CREATE TABLE IF NOT EXISTS delivery(id INTEGER PRIMARY KEY AUTOINCREMENT,event_key TEXT NOT NULL UNIQUE,origin TEXT NOT NULL,body TEXT NOT NULL,mode TEXT NOT NULL)');
    tool=world.tools()[0];
    return {character,botId:status.botId,core:clientVersions.coreVersion,tool:STARPOST_TOOL_DECLS[0]};
  }
  if(!tool)throw Error('星邮未完成初始化');
  if(op==='start'){if(!started){started=true;await world.start(host);}return true;}
  if(op==='pull'){
    const row=db.prepare("SELECT id,body,mode FROM delivery WHERE mode!='pending' ORDER BY id LIMIT 1").get();
    return row?{id:row.id,mode:row.mode,event:JSON.parse(row.body)}:null;
  }
  if(op==='ack'){db.prepare('DELETE FROM delivery WHERE id=?').run(args.id);return true;}
  if(op==='call'){
    const views=[];
    const value=await toolViews.run(views,()=>tool.handler({family:args.family,action:args.action,argsJson:args.argsJson}));
    return {value,views};
  }
  throw Error('未知本地操作');
}

const tasks=new Set();
async function dispatch(line){
  let id;
  try{
    const msg=JSON.parse(line);
    id=msg.id;
    const result=await request(msg.op,msg.args||{});
    process.stdout.write(JSON.stringify({id,result})+'\n');
  }catch(error){process.stdout.write(JSON.stringify({id,error:error.message})+'\n');}
}
const lines=createInterface({input:process.stdin});
lines.on('line',line=>{const p=dispatch(line);tasks.add(p);p.finally(()=>tasks.delete(p));});
lines.on('close',async()=>{
  await world?.stop();
  await Promise.allSettled([...tasks]);
  await world?.stop();
  db?.close();unlock?.();
});
