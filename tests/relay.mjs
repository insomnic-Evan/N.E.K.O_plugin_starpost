// Isolated loopback relay used by the plugin integration test.
import {createInterface} from 'node:readline';
import {join} from 'node:path';
import {pathToFileURL} from 'node:url';
const {createStarpostServer}=await import(process.env.STARPOST_TEST_RELAY ? pathToFileURL(process.env.STARPOST_TEST_RELAY).href : 'cortico-world-starpost/server/server.mjs');
const key='p'.repeat(32);
const relay=createStarpostServer({file:join(process.argv[2],'relay.json'),keys:{10001:key},port:0,clock:()=>Date.parse('2026-11-07T18:00:00+08:00')});
await relay.listen();
const url='http://127.0.0.1:'+relay.server.address().port;
console.log(JSON.stringify({url}));
for await(const line of createInterface({input:process.stdin})){
  const {op,target,text}=JSON.parse(line);
  if(op==='befriend')relay.store.befriend(target,'10001');
  else if(op==='owner')relay.store.emit([target],'owner.message',{id:'neko-owner',text,sender:'10001H',address:'测试用户',sourceProject:'starpost'});
  else if(op==='private'){
    const response=await fetch(url+'/rpc',{method:'POST',headers:{'content-type':'application/json','x-starpost-id':'10001',authorization:'Bearer '+key},body:JSON.stringify({action:'message.send',args:{kind:'private',target,text}})});
    const reply=await response.json();if(!reply.ok)throw Error(reply.error);
  }else if(op==='quit')break;
  console.log('{}');
}
await relay.close();

