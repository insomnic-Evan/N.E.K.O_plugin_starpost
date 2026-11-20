import {readFileSync} from 'node:fs';
import {join, resolve} from 'node:path';
import {homedir} from 'node:os';
import {parseArgs} from 'node:util';
import {loadSettings, lock, makeWorld, options, pinServer, saveSettings} from './runtime/src/local.mjs';

const usage = `node account.mjs hub-login --character 角色名 | hub-complete | hub-cancel | status
node account.mjs login --character 角色名 --file 凭据.json | register --character 角色名
node account.mjs configure [--mode active|mixed|passive] [--square-mode manual|digest|realtime]
    [--feed-mode manual|digest|realtime] [--digest-interval-ms 毫秒] [--emoji-dir 目录]`;
async function main() {
  const [action, ...args] = process.argv.slice(2);
  if (!action || action==='--help') return console.log(usage);
  if (!['status','hub-login','hub-complete','hub-cancel','register','login','configure'].includes(action)) throw Error(usage);
  const flags = ['character','mode','square-mode','feed-mode','digest-interval-ms','emoji-dir','file','server','hub'];
  const {values} = parseArgs({args,options:Object.fromEntries(flags.map(key=>[key,{type:'string'}]))});
  const dir = resolve(process.env.STARPOST_NEKO_HOME || join(homedir(),'.starpost','neko'));
  const release = action==='status' ? ()=>{} : lock(dir);
  try {
    const cfg = loadSettings(dir);
    for (const [flag,key] of Object.entries({character:'sessionId',mode:'receiveMode','square-mode':'squareMode','feed-mode':'feedMode','emoji-dir':'emojiDir',server:'serverUrl',hub:'hubUrl'})) {
      if(values[flag]!==undefined) cfg[key]=values[flag].trim();
    }
    if(values['digest-interval-ms']!==undefined) cfg.digestIntervalMs=Number(values['digest-interval-ms']);
    if(action!=='status' && (!cfg.sessionId || cfg.sessionId.length>128 || /[\x00-\x1f]/.test(cfg.sessionId))) throw Error('请用 --character 指定本机的角色名');
    const effective=options(cfg,dir);
    const invoke=makeWorld(dir,cfg).webUi().invoke;
    const before=await invoke('viewer','status',[]);
    let pairing;
    if(action==='hub-login'){
      pinServer(dir,cfg);
      pairing=await invoke('viewer','hubBegin',['星邮 N.E.K.O. · '+cfg.sessionId.slice(0,48)]);
    } else if(action==='hub-complete') pairing=await invoke('viewer','hubFinish',[]);
    else if(action==='hub-cancel') await invoke('viewer','hubCancel',[]);
    else if(action==='login'){
      if(!values.file) throw Error('请通过 --file 选择本机凭据 JSON');
      const data=readFileSync(values.file,'utf8').replace(/^\uFEFF/,'');
      const id=JSON.parse(data).botId;
      if(before.registered && before.botId!==id) throw Error('更换账号请使用独立的 STARPOST_NEKO_HOME 目录');
      pinServer(dir,cfg);
      await invoke('viewer','login',[id,data]);
    } else if(action==='register'){
      if(before.registered) throw Error('当前已有星邮账号');
      pinServer(dir,cfg);await invoke('viewer','register',[]);
    }
    if(action!=='status') saveSettings(dir,cfg);
    const status=await invoke('viewer','status',[]), hub=await invoke('viewer','hubStatus',[]);
    console.log(JSON.stringify({registered:status.registered,botId:status.botId,character:cfg.sessionId,mode:effective.receiveMode,notifications:effective.notifications,hub:hub.mode,pairing:hub.pending,pairingStatus:pairing?.status,message:pairing?.message,directory:dir},null,2));
  } finally {release();}
}
main().catch(error=>{console.error(error instanceof SyntaxError?'配置或凭据文件不是有效的 JSON':error.message);process.exitCode=1;});

