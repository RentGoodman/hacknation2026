import {createToolSession} from '../chat-tools.mjs';
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {validateInput,groundResponse,createChatService,loadChatData} from '../chat-server.mjs';
import {readFile} from 'node:fs/promises';
const source={doc_id:'D001',jurisdictions:'Test city',url:'https://example.org/law',text:'Security must be returned within 21 days after the tenant leaves.',retrieved_at:'2026-10-01'};
const property={id:'A0001',city:'test',address:'1 Main St',units:4,year:1920};
const rule={team_rule_id:'r-1',source_doc_id:'D001',title:'Deposit return',category:'security_deposits',quoted_span:source.text};
const D={snapshot:'2026-10-01',properties:[property],cities:{test:{name:'Test city'}},sources:[source],readings:[{id:'preview-1',doc_id:'D001',summary:'Manual preview',quote:'Unverified preview sentence.'}],change_tests:[]};
const E={rules:{'r-1':rule},buildings:{A0001:{}},texts:['Coverage uncertain'],lookups:{'2026-10-01':{A0001:[['r-1','unknown',0,true]]}},changes:{},rules_sha256:'known'};
const input={message:'How long to return the deposit?',address_id:'A0001',as_of:'2026-10-01'};
const session=createToolSession({data:{D,E},input});
await session.execute('get_rules',{address_id:input.address_id,as_of:input.as_of});
await session.execute('get_sources',{rule_ids:['r-1']});
const {evidence}=session;
const raw={paragraphs:[{text:'The source specifies 21 days.',citations:[{source_id:'D001',quote:'returned within 21 days after the tenant leaves.'}]}],actions:[]};
test('rejects unknown properties, invalid dates, languages and oversized questions',()=>{for(const override of [{address_id:'A9999'},{as_of:'2026-02-30'},{language:'fr'},{message:' '},{message:'x'.repeat(1501)}])assert.throws(()=>validateInput({...input,...override},D));assert.equal(validateInput({...input,language:'es'},D).language,'es');});
test('source links come from server data and passages are verified',()=>{const r=groundResponse(raw,evidence,{D,E},input);assert.match(r.text,/\[1\]/);assert.equal(r.sources[0].url,source.url);assert.equal(r.sources[0].quote,raw.paragraphs[0].citations[0].quote);});
test('rejects fabricated citations and fabricated passages',()=>{for(const c of [{source_id:'D999',quote:source.text},{source_id:'D001',quote:'Deposits must be returned within 90 days.'}])assert.throws(()=>groundResponse({paragraphs:[{text:'Claim',citations:[c]}]},evidence,{D,E},input),/citation could not be verified/);});
test('drops unsupported actions and nonexistent data IDs',()=>{const r=groundResponse({...raw,actions:[{type:'email',label:'Send'},{type:'rule',label:'Review',ruleId:'made-up'},{type:'facts',label:'Facts'}]},evidence,{D,E},input);assert.equal(r.actions.length,1);assert.equal(r.actions[0].propertyId,'A0001');});
test('model chooses tools; tool results feed subsequent requests before final answer',async()=>{
 const requests=[];
 const use=(id,name,input)=>({type:'tool_use',id,name,input});
 const responses=[
  {stop_reason:'tool_use',content:[use('facts','get_building_facts',{address_id:'A0001'}),use('rules','get_rules',{address_id:'A0001',as_of:input.as_of,topic:'security_deposits'})]},
  {stop_reason:'tool_use',content:[use('source','get_sources',{rule_ids:['r-1']})]},
  {stop_reason:'end_turn',content:[{type:'text',text:JSON.stringify(raw)}]}
 ];
 const chat=createChatService({data:{D,E},config:{key:'test-key',model:'test-model'},lookup:()=>assert.fail(),fetchImpl:async(url,r)=>{assert.equal(url,'https://api.anthropic.com/v1/messages');requests.push(JSON.parse(r.body));return {ok:true,json:async()=>responses.shift()};}});
 const r=await chat({...input,history:[{question:'Earlier question',answer:{text:'Earlier answer'},address:property.address,asOf:input.as_of}]});
 assert.equal(requests.length,3);assert.equal(requests[0].messages[1].content,'Earlier answer');assert.match(requests[0].system,/interface_language/);
 const initial=JSON.parse(requests[0].messages.at(-1).content).context;assert.equal(initial.property.id,input.address_id);assert.equal(initial.interface_language,'en');assert.equal(initial.verdicts,undefined);assert.equal(initial.sources,undefined);
 const results=requests[1].messages.at(-1).content;assert.equal(results.length,2);const rules=JSON.parse(results.find(r=>r.tool_use_id==='rules').content);assert.equal(rules.verdicts[0].result,'unknown');assert.equal(rules.verdicts[0].conflict,true);
 const sources=JSON.parse(requests[2].messages.at(-1).content[0].content).sources;assert.equal(sources[0].previews[0].summary,'Manual preview');
 assert.equal(r.sources.length,1);assert.equal(r.tool_trace.length,3);assert.ok(r.tool_trace.every(t=>t.ok));
});
test('tool scope cannot change the tagged address/date or read unrequested rule sources',async()=>{
 const s=createToolSession({data:{D,E},input});
 await assert.rejects(s.execute('get_building_facts',{address_id:'A9999'}),/tagged address/);
 await assert.rejects(s.execute('get_rules',{address_id:input.address_id,as_of:'2027-01-01'}),/selected/);
 await assert.rejects(s.execute('get_sources',{rule_ids:['r-1']}),/returned by get_rules/);
 await assert.rejects(s.execute('run_shell',{command:'anything'}),/Unknown tool/);
});
test('preview prose is returned but cannot be used as verified evidence',()=>{
 assert.throws(()=>groundResponse({paragraphs:[{text:'Claim',citations:[{source_id:'D001',quote:'Unverified preview sentence.'}]}]},evidence,{D,E},input),/citation could not be verified/);
});
test('source evidence is isolated to the current request',()=>{
 const fresh=createToolSession({data:{D,E},input});assert.throws(()=>groundResponse(raw,fresh.evidence,{D,E},input),/citation could not be verified/);
});
test('no API key produces a clear failure, never a canned answer',async()=>{const chat=createChatService({data:{D,E},config:{},lookup:()=>assert.fail(),fetchImpl:()=>assert.fail()});await assert.rejects(chat(input),/key is not configured/);});
test('stale engine results fail without returning verdicts',async()=>{const s=createToolSession({data:{D,E},input:{...input,as_of:'2026-10-03'},lookup:async()=>({rules_sha256:'stale',lookups:[]})});await assert.rejects(s.execute('get_rules',{address_id:input.address_id,as_of:'2026-10-03'}),/engine data changed/);assert.equal(s.retrievedRules.size,0);});
test('provider failures do not disclose provider body or credentials',async()=>{const chat=createChatService({data:{D,E},config:{key:'test'},fetchImpl:async()=>({ok:false,status:401,text:async()=>'secret upstream debug'})});await assert.rejects(chat(input),e=>e.status===502&&!e.message.includes('secret'));});

test('repeated tools are bounded and final model request disables tools',async()=>{
 let count=0;const chat=createChatService({data:{D,E},config:{key:'test'},fetchImpl:async(url,r)=>{const req=JSON.parse(r.body);count++;if(count===6)assert.equal(req.tool_choice.type,'none');return {ok:true,json:async()=>({content:[{type:'tool_use',id:String(count),name:'get_building_facts',input:{address_id:input.address_id}}]})};}});
 await assert.rejects(chat(input),/tool limit/);assert.equal(count,6);
});
test('concurrent rule calls share a single dated engine lookup',async()=>{
 let calls=0;const s=createToolSession({data:{D,E},input:{...input,as_of:'2026-10-03'},lookup:async()=>{calls++;return {rules_sha256:'known',lookups:[{team_rule_id:'r-1',result:'unknown',explanation:'Missing facts'}]};}});
 const a={address_id:input.address_id,as_of:'2026-10-03'};await Promise.all([s.execute('get_rules',a),s.execute('get_rules',{...a,topic:'security_deposits'})]);assert.equal(calls,1);
});
test('unavailable original text does not turn preview into citation evidence',async()=>{
 const s=createToolSession({data:{D:{...D,sources:[{...source,text:null}]},E},input});await s.execute('get_rules',{address_id:input.address_id,as_of:input.as_of});const r=await s.execute('get_sources',{rule_ids:['r-1']});assert.equal(r.sources[0].text_available,false);assert.equal(r.sources[0].previews.length,1);assert.equal(s.evidence.size,0);
});

test('packaged rule sources reach the tools and citation renderer, including all restored and supplemental documents',async()=>{
 const data=await loadChatData(new URL('../dist/',import.meta.url));
 const rules=Object.values(data.E.rules);
 const request={message:'Read sources',address_id:'A0016',as_of:'2026-10-03'};
 const s=createToolSession({data,input:request,lookup:async()=>({rules_sha256:data.E.rules_sha256,lookups:rules.map(r=>({team_rule_id:r.team_rule_id,result:'unknown',explanation:'Source retrieval test'}))})});
 await s.execute('get_rules',{address_id:request.address_id,as_of:request.as_of});
 for(let i=0;i<rules.length;i+=8){
  const result=await s.execute('get_sources',{rule_ids:rules.slice(i,i+8).map(r=>r.team_rule_id)});
  assert.ok(result.sources.every(source=>source.text_available&&source.excerpts.length));
 }
 assert.ok(new Set(rules.map(r=>r.source_doc_id)).has('DX20'));
 assert.ok(new Set(rules.map(r=>r.source_doc_id)).has('DX21'));
 for(const rule of rules){
  const source=data.D.sources.find(s=>s.doc_id===rule.source_doc_id);
  const file=await readFile(new URL('../dist/'+source.local_path,import.meta.url),'utf8');
  assert.equal(file,source.text);
  const answer=groundResponse({paragraphs:[{text:'Source passage',citations:[{source_id:source.doc_id,quote:rule.quoted_span}]}]},s.evidence,data,request);
  assert.equal(answer.sources[0].url,source.url);
  assert.equal(answer.sources[0].docId,source.doc_id);
 }
});
