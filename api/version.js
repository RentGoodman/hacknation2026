import {readFile} from 'node:fs/promises';
import {json} from '../mockup/api-handlers.mjs';

let versionPromise;
export default async function handler(req,res){
 if(!['GET','HEAD'].includes(req.method)){res.setHeader('Allow','GET, HEAD');return json(res,405,{error:'Method not allowed'});}
 try{
  const version=await (versionPromise??=readFile(new URL('../mockup/dist/data/version.json',import.meta.url),'utf8').then(JSON.parse));
  if(req.method==='HEAD'){res.writeHead(200,{'Content-Type':'application/json','Cache-Control':'no-store'});return res.end();}
  json(res,200,version);
 }catch{json(res,503,{error:'Build identity unavailable'});}
}
