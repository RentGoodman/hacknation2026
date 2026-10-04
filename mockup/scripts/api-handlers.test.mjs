import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {EventEmitter} from 'node:events';
import {createChatHandler,createRemoteLookup} from '../api-handlers.mjs';
import {ChatError,loadChatConfig} from '../chat-server.mjs';
import vercelChat from '../../api/chat.js';
import vercelVersion from '../../api/version.js';

async function server(t,handler){
 const http=createServer(handler);await new Promise(resolve=>http.listen(0,'127.0.0.1',resolve));
 t.after(()=>new Promise(resolve=>http.close(resolve)));
 return `http://127.0.0.1:${http.address().port}`;
}
const post=(url,body,headers={})=>fetch(url,{method:'POST',headers:{'Content-Type':'application/json',...headers},body:typeof body==='string'?body:JSON.stringify(body)});

test('chat HTTP transport handles JSON, custom origins, validation and safe failures',async t=>{
 const url=await server(t,createChatHandler(async()=>async body=>{
  if(body.fail)throw new Error('secret provider body');
  if(body.noKey)throw new ChatError(503,'The chat API key is not configured on this server.');
  return {text:body.message};
 }));
 const good=await post(url,{message:'Hello'},{Origin:url});assert.equal(good.status,200);assert.deepEqual(await good.json(),{text:'Hello'});assert.equal(good.headers.get('cache-control'),'no-store');
 assert.equal((await fetch(url)).status,405);
 assert.equal((await post(url,{}, {Origin:'https://unrelated.example'})).status,403);
 assert.equal((await post(url,{}, {'Content-Type':'text/plain'})).status,415);
 assert.equal((await post(url,'{')).status,400);
 assert.equal((await post(url,{message:'x'.repeat(65536)})).status,413);
 assert.equal((await post(url,{noKey:true})).status,503);
 const failed=await post(url,{fail:true});assert.equal(failed.status,502);assert.doesNotMatch(await failed.text(),/secret provider/);
});

test('chat supports Vercel pre-parsed bodies and enforces their size',async()=>{
 const handler=createChatHandler(async()=>async body=>({text:body.message}));
 for(const [body,status] of [[{message:'Parsed'},200],['{',400],[{message:'x'.repeat(65536)},413]]){
  const req={method:'POST',headers:{host:'preview.vercel.app',origin:'https://preview.vercel.app','content-type':'application/json'},body};
  const res=new EventEmitter();res.setHeader=()=>{};res.writeHead=s=>res.status=s;res.end=()=>{res.writableEnded=true;};
  await handler(req,res);assert.equal(res.status,status);
 }
});

test('remote engine lookup uses deployment identity and forwards protection credentials',async()=>{
 const req={headers:{host:'untrusted.example',cookie:'_vercel_jwt=browser-session','x-vercel-protection-bypass':'request-bypass'}};
 const lookup=createRemoteLookup(req,undefined,{env:{VERCEL_URL:'parcel-deployment.vercel.app',VERCEL_AUTOMATION_BYPASS_SECRET:'server-bypass'},fetchImpl:async(url,options)=>{
  assert.equal(url.origin,'https://parcel-deployment.vercel.app');assert.equal(url.pathname,'/api/lookup');assert.equal(url.searchParams.get('address'),'A0001');assert.equal(url.searchParams.get('as_of'),'2026-10-03');
  assert.equal(options.headers.cookie,req.headers.cookie);assert.equal(options.headers['x-vercel-protection-bypass'],'server-bypass');assert.equal(options.redirect,'error');assert.ok(options.signal);
  return {ok:true,json:async()=>({lookups:[]})};
 }});
 assert.deepEqual(await lookup('A0001','2026-10-03'),{lookups:[]});
 assert.throws(()=>createRemoteLookup(req,undefined,{env:{VERCEL_URL:'evil.example'}}),/deployment URL/);
});

test('hosted chat configuration uses environment secrets and ignores local env files',async()=>{
 const saved={...process.env};
 try{
  process.env.VERCEL='1';process.env.ANTHROPIC_API_KEY='test-key';process.env.PARCEL_ENV_FILE='/missing/private/env';process.env.PARCEL_CHAT_MODEL='configured-model';
  assert.deepEqual(await loadChatConfig(),{key:'test-key',model:'configured-model'});
 }finally{for(const key of ['VERCEL','ANTHROPIC_API_KEY','PARCEL_ENV_FILE','PARCEL_CHAT_MODEL']){if(saved[key]===undefined)delete process.env[key];else process.env[key]=saved[key];}}
});

test('actual Vercel chat entrypoint calls Anthropic and Python lookup for an uncached date',async t=>{
 const saved={...process.env},realFetch=globalThis.fetch;
 const date='2026-10-03';let modelCalls=0,lookupCalls=0;
 try{
  process.env.VERCEL='1';process.env.VERCEL_URL='parcel-deployment.vercel.app';process.env.ANTHROPIC_API_KEY='test-key';
  globalThis.fetch=async(url,options)=>{
   if(String(url).startsWith('https://api.anthropic.com/')){
    assert.equal(options.headers['x-api-key'],'test-key');modelCalls++;
    return {ok:true,json:async()=>({content:modelCalls===1?[{type:'tool_use',id:'rules',name:'get_rules',input:{address_id:'A0001',as_of:date}}]:[{type:'text',text:JSON.stringify({paragraphs:[{text:'The lookup completed.',citations:[]}],actions:[]})}]})};
   }
   if(String(url).startsWith('https://parcel-deployment.vercel.app/api/lookup')){
    lookupCalls++;
    const {loadChatData}=await import('../chat-server.mjs');const {E}=await loadChatData(new URL('../dist/',import.meta.url));
    return {ok:true,json:async()=>({rules_sha256:E.rules_sha256,lookups:[]})};
   }
   return realFetch(url,options);
  };
  const url=await server(t,vercelChat);
  const r=await post(url,{message:'What rules apply?',address_id:'A0001',as_of:date},{Origin:url});assert.equal(r.status,200);assert.equal((await r.json()).tool_trace[0].ok,true);assert.equal(modelCalls,2);assert.equal(lookupCalls,1);
 }finally{globalThis.fetch=realFetch;for(const key of ['VERCEL','VERCEL_URL','ANTHROPIC_API_KEY']){if(saved[key]===undefined)delete process.env[key];else process.env[key]=saved[key];}}
});

test('Vercel build identity endpoint serves GET and HEAD',async t=>{
 const url=await server(t,vercelVersion),r=await fetch(url);assert.equal(r.status,200);assert.match((await r.json()).rules_sha256,/^[a-f0-9]{64}$/);
 const head=await fetch(url,{method:'HEAD'});assert.equal(head.status,200);assert.equal(await head.text(),'');assert.equal((await post(url,{})).status,405);
});
