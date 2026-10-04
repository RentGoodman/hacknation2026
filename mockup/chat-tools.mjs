export class ToolInputError extends Error{}
const normalize=s=>String(s||'').replace(/\s+/g,' ').trim();
const string={type:'string'};
const schema=(properties,required=Object.keys(properties))=>({type:'object',properties,required,additionalProperties:false});
const topics=['all','rent_increase_limits','just_cause_eviction','security_deposits','application_screening_fees','screening_restrictions','algorithmic_rent_setting'];
export const CHAT_TOOLS=[
 {name:'get_building_facts',description:'Read the selected property’s building facts, legal jurisdiction and missing coverage conditions. Use before deciding whether a rule applies to this building. Supply the tagged address_id; this tool cannot silently switch the selected property. Missing facts remain unknown.',input_schema:schema({address_id:string})},
 {name:'get_rules',description:'Retrieve engine rule results for the tagged property and selected date, optionally filtered by legal topic. Returns requirements, exemptions, applicability, conflicts, rule IDs and source document IDs. These are extracted results, not original evidence: call get_sources before making legal claims. With topic all also returns recorded change scenarios for the selected city; scenario dates can differ from the requested date.',input_schema:schema({address_id:string,as_of:string,topic:{type:'string',enum:topics}},['address_id','as_of'])},
 {name:'get_sources',description:'Read original source passages and the curated Source previews for rule IDs previously returned by get_rules in this request. Previews are manual summaries, not citation evidence. Only original excerpts may be quoted. Returns capture dates, URLs, text availability, and pagination for longer documents. Use offset to read another page when a relevant condition is missing; query helps select passages near matching terms. Never infer the content of unavailable source text.',input_schema:schema({rule_ids:{type:'array',items:string,minItems:1,maxItems:8},query:string,offset:{type:'integer',minimum:0}},['rule_ids'])}
];
export function createToolSession({data,input,lookup}){
 const {D,E}=data,property=D.properties.find(p=>p.id===input.address_id);
 const evidence=new Map(),retrievedRules=new Set();let lookupsPromise;
 function args(value,keys,required){if(!value||typeof value!=='object'||Array.isArray(value)||Object.keys(value).some(k=>!keys.includes(k))||required.some(k=>value[k]===undefined))throw new ToolInputError('Invalid tool arguments.');}
 function address(id){if(id!==input.address_id)throw new ToolInputError('Use the tagged address_id. Ask the user to change the address tag to inspect another property.');}
 async function verdicts(){
  if(!lookupsPromise)lookupsPromise=(async()=>{
   const entries=E.lookups[input.as_of]?.[input.address_id];
   if(entries)return entries.map(([id,result,t,c])=>({id,result,explanation:E.texts[t],conflict:!!c}));
   const dated=await lookup(input.address_id,input.as_of);
   if(dated.rules_sha256!==E.rules_sha256)throw new ToolInputError('The engine data changed. Refresh the data before using the chat.');
   return dated.lookups.map(v=>({id:v.team_rule_id,result:v.result,explanation:v.explanation,conflict:!!v.conflict_flag}));
  })();
  return lookupsPromise;
 }
 async function execute(name,a){
  if(name==='get_building_facts'){
   args(a,['address_id'],['address_id']);address(a.address_id);
   return {address_id:input.address_id,as_of:input.as_of,property,building:E.buildings[property.id]||{},snapshot:D.snapshot};
  }
  if(name==='get_rules'){
   args(a,['address_id','as_of','topic'],['address_id','as_of']);address(a.address_id);
   if(a.as_of!==input.as_of)throw new ToolInputError('Use the date selected in the interface.');
   const topic=a.topic||'all';if(!topics.includes(topic))throw new ToolInputError('Unknown legal topic.');
   const vs=(await verdicts()).filter(v=>E.rules[v.id]&&(topic==='all'||E.rules[v.id].category===topic)).map(v=>{
    retrievedRules.add(v.id);const {quoted_span,...rule}=E.rules[v.id];return {...v,rule};
   });
   const result={address_id:property.id,as_of:input.as_of,topic,verdicts:vs};
   if(topic==='all')result.scenarios=(D.change_tests||[]).map(t=>({...t,affected_in_selected_city:(E.changes[t.test_id]?.affected_address_ids||[]).filter(id=>D.properties.some(p=>p.id===id&&p.city===property.city)),notes:E.changes[t.test_id]?.notes}));
   return result;
  }
  if(name==='get_sources'){
   args(a,['rule_ids','query','offset'],['rule_ids']);
   if(!Array.isArray(a.rule_ids)||!a.rule_ids.length||a.rule_ids.length>8||a.rule_ids.some(id=>typeof id!=='string'||!retrievedRules.has(id)))throw new ToolInputError('Supply 1–8 rule IDs returned by get_rules for this address.');
   if(a.query!==undefined&&(typeof a.query!=='string'||a.query.length>300))throw new ToolInputError('Source query must be at most 300 characters.');
   const offset=a.offset??0;if(!Number.isInteger(offset)||offset<0||offset>2000000)throw new ToolInputError('Invalid source offset.');
   const rules=[...new Set(a.rule_ids)].map(id=>E.rules[id]);
   const docs=[...new Set(rules.map(r=>r.source_doc_id))];
   return {sources:docs.map(id=>{
    const source=D.sources.find(s=>s.doc_id===id),text=normalize(source?.text);
    const previews=(D.readings||[]).filter(r=>r.doc_id===id).map(r=>({...r,evidence_type:'curated preview; verify claims in original excerpts'}));
    const base={id,url:source?.url||rules.find(r=>r.source_doc_id===id).source_url,captured:source?.retrieved_at||D.snapshot,title:source?.jurisdictions?`${source.jurisdictions} / ${id}`:id,previews};
    if(!text)return {...base,text_available:false,excerpts:[],note:'No original source text is available. Do not quote or assume the preview is verified.'};
    const excerpts=[text.slice(offset,offset+12000)].filter(Boolean);
    for(const rule of rules.filter(r=>r.source_doc_id===id)){
     const quote=normalize(rule.quoted_span),at=text.indexOf(quote);
     if(quote&&at>=0)excerpts.push(text.slice(Math.max(0,at-400),Math.min(text.length,at+quote.length+700)));
    }
    const terms=(a.query||'').toLowerCase().split(/\s+/).filter(w=>w.length>3);
    if(terms.length){const ranked=source.text.split(/\n\s*\n/).map(normalize).map(t=>({text:t,score:terms.reduce((n,w)=>n+Number(t.toLowerCase().includes(w)),0)})).filter(p=>p.score).sort((a,b)=>b.score-a.score).slice(0,2);excerpts.push(...ranked.map(p=>p.text.slice(0,5000)));}
    const unique=[...new Set(excerpts)],prior=evidence.get(id);
    evidence.set(id,{...base,excerpts:[...new Set([...(prior?.excerpts||[]),...unique])]});
    return {...base,text_available:true,excerpts:unique,offset,next_offset:offset+12000<text.length?offset+12000:null};
   })};
  }
  throw new ToolInputError('Unknown tool. Use get_building_facts, get_rules or get_sources.');
 }
 return {execute,evidence,retrievedRules};
}
