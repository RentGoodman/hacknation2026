import {ChatError} from './chat-server.mjs';

export function json(res,status,value){
 res.writeHead(status,{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store'});
 res.end(JSON.stringify(value));
}

function sameOrigin(req){
 if(!req.headers.host)return false;
 if(!req.headers.origin)return true;
 try{
  const origin=new URL(req.headers.origin);
  return ['http:','https:'].includes(origin.protocol)&&origin.host===req.headers.host;
 }catch{return false;}
}

async function readBody(req){
 const limit=65536;
 if(Number(req.headers['content-length'])>limit)throw new ChatError(413,'Question is too large.');
 if(req.body!==undefined){
  const raw=Buffer.isBuffer(req.body)?req.body.toString('utf8'):typeof req.body==='string'?req.body:JSON.stringify(req.body);
  if(Buffer.byteLength(raw)>limit)throw new ChatError(413,'Question is too large.');
  try{return JSON.parse(raw);}catch{throw new ChatError(400,'Invalid JSON.');}
 }
 const chunks=[];let bytes=0;
 for await(const chunk of req){bytes+=Buffer.byteLength(chunk);if(bytes>limit)throw new ChatError(413,'Question is too large.');chunks.push(Buffer.from(chunk));}
 try{return JSON.parse(Buffer.concat(chunks).toString('utf8'));}catch{throw new ChatError(400,'Invalid JSON.');}
}

export function createChatHandler(getService){
 let activeChats=0;
 return async(req,res)=>{
  if(req.method!=='POST'){res.setHeader('Allow','POST');return json(res,405,{error:'Method not allowed'});}
  if(!sameOrigin(req))return json(res,403,{error:'Origin not allowed'});
  if(!/^application\/json(?:\s*;|$)/i.test(req.headers['content-type']||''))return json(res,415,{error:'JSON required'});
  if(activeChats>=2)return json(res,429,{error:'A conversation is already running. Please retry shortly.'});
  activeChats++;
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),95000);
  const onClose=()=>{if(!res.writableEnded)controller.abort();};
  res.on('close',onClose);
  try{
   const body=await readBody(req),answerChat=await getService(req,controller.signal);
   const answer=await answerChat(body,controller.signal);
   if(!res.destroyed)json(res,200,answer);
  }catch(error){
   if(!res.destroyed)json(res,error instanceof ChatError?error.status:502,{error:controller.signal.aborted?'The answer took too long. Please try again.':error instanceof ChatError?error.message:'The chat is temporarily unavailable. Please try again.'});
  }finally{clearTimeout(timer);res.off('close',onClose);activeChats--;}
 };
}

export function createRemoteLookup(req,signal,{env=process.env,fetchImpl=fetch}={}){
 const host=env.VERCEL_URL;
 if(!host||! /^[a-z0-9.-]+\.vercel\.app$/i.test(host))throw new Error('Missing Vercel deployment URL');
 const headers={};
 if(req.headers.cookie)headers.cookie=req.headers.cookie;
 const bypass=env.VERCEL_AUTOMATION_BYPASS_SECRET||req.headers['x-vercel-protection-bypass'];
 if(bypass)headers['x-vercel-protection-bypass']=bypass;
 return async(address,asOf)=>{
  const url=new URL('/api/lookup',`https://${host}`);
  url.search=new URLSearchParams({address,as_of:asOf}).toString();
  const response=await fetchImpl(url,{headers,redirect:'error',signal:signal?AbortSignal.any([signal,AbortSignal.timeout(15000)]):AbortSignal.timeout(15000)});
  if(!response.ok)throw new Error('Date lookup unavailable');
  return response.json();
 };
}
