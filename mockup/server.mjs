import {createChatHandler} from './api-handlers.mjs';
import {createChatService,loadChatData,loadChatConfig} from './chat-server.mjs';
import http from 'node:http';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {readFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {resolve,extname,sep} from 'node:path';
const runFile=promisify(execFile);
const lookupScript=fileURLToPath(new URL('./scripts/lookup-date.py',import.meta.url));
const repo=fileURLToPath(new URL('../',import.meta.url));
const root=fileURLToPath(new URL('./dist/',import.meta.url));
async function lookupDate(address,asOf,overrides={}){
 const args=[lookupScript,address,asOf];
 if(overrides.year_built!==undefined)args.push('--year-built',String(overrides.year_built));
 if(overrides.units!==undefined)args.push('--units',String(overrides.units));
 const {stdout}=await runFile(process.env.PARCEL_PYTHON||'python3',args,{cwd:repo,timeout:12000,maxBuffer:2*1024*1024});
 return JSON.parse(stdout);
}
const port=Number(process.env.PORT)||4173;
const host=process.env.HOST||'127.0.0.1';
const chatData=await loadChatData(new URL('./dist/',import.meta.url));
const chatConfig=await loadChatConfig();
const answerChat=createChatService({data:chatData,config:chatConfig,lookup:lookupDate});
const git=async(...args)=>{try{return (await runFile('git',args,{cwd:repo,timeout:5000})).stdout.trim()||null;}catch{return null;}};
async function buildVersion(){
 let rules=null;try{rules=createHash('sha256').update(await readFile(resolve(repo,'out/rules.json'))).digest('hex');}catch{}
 return {git_sha:process.env.VERCEL_GIT_COMMIT_SHA||await git('rev-parse','HEAD'),rules_sha256:rules,generated_at:process.env.PARCEL_BUILD_DATE||await git('log','-1','--format=%cI')};
}
let versionInfo;
const chatRoute=createChatHandler(async()=>answerChat);
const mime={'.html':'text/html; charset=utf-8','.css':'text/css; charset=utf-8','.js':'text/javascript; charset=utf-8','.ttf':'font/ttf','.png':'image/png','.svg':'image/svg+xml','.txt':'text/plain'};
http.createServer(async(req,res)=>{try{const url=new URL(req.url,'http://localhost');
if(url.pathname==='/api/chat')return await chatRoute(req,res);
if(url.pathname==='/api/version'){
 res.setHeader('Cache-Control','no-store');res.setHeader('Content-Type','application/json');
 if(req.method!=='GET'&&req.method!=='HEAD'){res.writeHead(405);return res.end('{"error":"Method not allowed"}');}
 res.writeHead(200);return res.end(JSON.stringify(await (versionInfo??=buildVersion())));
}
if(url.pathname==='/api/lookup'){
 res.setHeader('Cache-Control','no-store');res.setHeader('Content-Type','application/json');
 if(req.method!=='GET'){res.writeHead(405);return res.end('{"error":"Method not allowed"}');}
 const address=url.searchParams.get('address')||'',asOf=url.searchParams.get('as_of')||'';
 if(!chatData.D.properties.some(p=>p.id===address)||!/^\d{4}-\d{2}-\d{2}$/.test(asOf)||!Number.isFinite(Date.parse(asOf))||new Date(asOf).toISOString().slice(0,10)!==asOf){res.writeHead(400);return res.end('{"error":"Invalid address or date"}');}
 try{
  const year=url.searchParams.get('year_built'),units=url.searchParams.get('units');
  if(year!==null&&(!/^\d{4}$/.test(year)||Number(year)<1600||Number(year)>new Date().getFullYear())){res.writeHead(400);return res.end('{"error":"Invalid year built"}');}
  if(units!==null&&!/^(?:[1-9]\d{0,4}|100000)$/.test(units)){res.writeHead(400);return res.end('{"error":"Invalid unit count"}');}
  const overrides={};if(year!==null)overrides.year_built=year;if(units!==null)overrides.units=units;
  const result=await lookupDate(address,asOf,overrides);
  res.writeHead(200);return res.end(JSON.stringify(result));
 }catch{res.writeHead(503);return res.end('{"error":"Date lookup unavailable"}');}
}
const path=decodeURIComponent(url.pathname);const file=resolve(root,'.'+(path==='/'?'/index.html':path));if(!file.startsWith(root.endsWith(sep)?root:root+sep)){res.writeHead(403);return res.end('Forbidden');}const body=await readFile(file);res.writeHead(200,{'Content-Type':mime[extname(file)]||'application/octet-stream','Cache-Control':'no-cache'});res.end(body);}catch{res.writeHead(404);res.end('Not found');}}).listen(port,host,()=>console.log(`Parcel prototype: http://${host}:${port}`));
