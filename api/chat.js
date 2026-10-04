import {createChatService,loadChatData,loadChatConfig} from '../mockup/chat-server.mjs';
import {createChatHandler,createRemoteLookup} from '../mockup/api-handlers.mjs';

let dataPromise;
export default createChatHandler(async(req,signal)=>{
 const data=await (dataPromise??=loadChatData(new URL('../mockup/dist/',import.meta.url)));
 const config=await loadChatConfig();
 return createChatService({data,config,lookup:createRemoteLookup(req,signal)});
});
