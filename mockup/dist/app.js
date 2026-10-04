'use strict';
const $=s=>document.querySelector(s);
const icons={map:'<path d="m3 6 6-3 6 3 6-3v15l-6 3-6-3-6 3V6Z"/><path d="M9 3v15M15 6v15"/>',building:'<rect x="5" y="3" width="14" height="18" rx="1"/><path d="M9 7h1m4 0h1M9 11h1m4 0h1M9 15h1m4 0h1M10 21v-3h4v3"/>',pin:'<path d="M20 10c0 6-8 11-8 11S4 16 4 10a8 8 0 1 1 16 0Z"/><circle cx="12" cy="10" r="2.5"/>',search:'<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',shield:'<path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6l8-3Z"/><path d="m8 12 3 3 5-6"/>',rent:'<path d="m3 10 9-7 9 7M5 9v12h14V9M9 21v-7h6v7"/>',deposit:'<rect x="3" y="6" width="18" height="14" rx="2"/><path d="M3 10h18M7 15h3M7 3h10"/>',fee:'<path d="M6 3h12v18l-3-2-3 2-3-2-3 2V3ZM9 7h6M9 11h6M9 15h3"/>',screen:'<circle cx="9" cy="8" r="4"/><path d="M2 21v-3a7 7 0 0 1 12-5m2 4 2 2 4-5"/>',algorithm:'<rect x="6" y="6" width="12" height="12" rx="2"/><path d="M9 3v3m6-3v3M9 18v3m6-3v3M3 9h3m-3 6h3m12-6h3m-3 6h3M10 10h4v4h-4z"/>',calendar:'<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 3v4m10-4v4M3 11h18M7 15h3m4 0h3"/>',book:'<path d="M12 5c-3-2-6-2-10-1v15c4-1 7-1 10 1 3-2 6-2 10-1V4c-4-1-7-1-10 1Zm0 0v15"/>',activity:'<path d="M3 12h4l3-8 4 16 3-8h4"/>',info:'<circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10v1"/>',refresh:'<path d="M20 7v5h-5M4 17v-5h5"/><path d="M5 8a8 8 0 0 1 13-3l2 3M4 16l2 3a8 8 0 0 0 13-3"/>',focus:'<path d="M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5"/><circle cx="12" cy="12" r="4"/>',close:'<path d="m6 6 12 12M18 6 6 18"/>',chevron:'<path d="m9 5 7 7-7 7"/>',bookmark:'<path d="M6 3h12v18l-6-4-6 4V3Z"/>',check:'<path d="m5 12 4 4L19 6"/>',external:'<path d="M14 3h7v7m0-7L10 14M10 3H3v18h18v-7"/>',clock:'<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>'};
const icon=n=>`<svg class="icon" viewBox="0 0 24 24" aria-hidden="true">${icons[n]||icons.info}</svg>`;
function hydrate(root=document){root.querySelectorAll('[data-icon]').forEach(e=>e.innerHTML=icon(e.dataset.icon));}
const I18N={
 en:{explore:'Explore properties',changes:'Law changes',sources:'Source library',warning:'Not legal advice',applies:'Applies',unknown:'Applicability unconfirmed',superseded:'Replaced by another rule',not_yet_effective:'Not yet effective',pending:'Pending proposal',why:'Why and source',missing:'Missing facts',confidence:'Confidence',open_source:'Open original source',retrieved:'Retrieved',effective:'Effective',human_review:'Human review recommended',rules:'Rules',facts:'Building facts',previews:'Source previews',building_rules:'Building rules',no_rule:'Proved absence of a rule',unresolved:'Unresolved corpus gaps'},
 es:{explore:'Explorar propiedades',changes:'Cambios legales',sources:'Biblioteca de fuentes',warning:'No es asesoramiento legal',applies:'Se aplica',unknown:'Aplicación sin confirmar',superseded:'Sustituida por otra regla',not_yet_effective:'Aún no vigente',pending:'Propuesta pendiente',why:'Motivo y fuente',missing:'Datos faltantes',confidence:'Confianza',open_source:'Abrir fuente original',retrieved:'Consultada',effective:'Vigente',human_review:'Revisión humana recomendada',rules:'Reglas',facts:'Datos del edificio',previews:'Fuentes',building_rules:'Reglas del edificio',no_rule:'Ausencia de regla demostrada',unresolved:'Lagunas no resueltas del corpus'}
};
let language=localStorage.getItem('parcel-language')==='es'?'es':'en';
const tr=k=>I18N[language][k]||I18N.en[k]||k;
const categories=[['rent',{en:'Rent increase limits',es:'Límites de aumento'},'green'],['shield',{en:'Just-cause eviction',es:'Desalojo con causa'},'blue'],['deposit',{en:'Security deposits',es:'Depósitos de garantía'},'purple'],['fee',{en:'Application & fees',es:'Solicitudes y cargos'},'amber'],['screen',{en:'Screening restrictions',es:'Restricciones de selección'},'teal'],['algorithm',{en:'Algorithmic pricing',es:'Precios algorítmicos'},'rose']];
const categoryLabel=()=>Object.fromEntries(categories.map(([id,label])=>[id,label[language]]));
const D=window.PARCEL_DATA,E=window.ENGINE_DATA;
const catOf={rent_increase_limits:'rent',just_cause_eviction:'shield',security_deposits:'deposit',application_screening_fees:'fee',screening_restrictions:'screen',algorithmic_rent_setting:'algorithm'};
const resultKind={applies:'applies',unknown:'unknown',superseded:'superseded',not_yet_effective:'future',pending:'pending'};
const resultOrder=['applies','unknown','not_yet_effective','pending','superseded'];
const properties=D.properties, cities=D.cities;
const sourcesById=Object.fromEntries(D.sources.map(s=>[s.doc_id,s]));
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const safeUrl=u=>/^https?:\/\//.test(u)?esc(u):'#';
let selected=properties.find(p=>p.id==='A0016')||properties[0];
let detailTab='rules',view='explore',audience='tenant',markers=[],enabled=new Set(categories.map(c=>c[0])),saved=new Set(),sourceFilter='all',map,changeOverlay=null;
const factOverrides=new Map();
function localToday(){const now=new Date();return `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}-${String(now.getDate()).padStart(2,'0')}`;}
$('#as-of').value=E.default_date||localToday();
const datedResults=new Map();
const narrowDateLayout=matchMedia('(max-width:650px)');
function placeDateControl(){const control=$('.time-control');if(narrowDateLayout.matches)$('.map-workspace').append(control);else $('.sidebar').insertBefore(control,$('.sidebar-tabs'));}
placeDateControl();
narrowDateLayout.addEventListener('change',placeDateControl);
const date=()=>$('#as-of').value||localToday();
function shortDate(d){return new Date(d.slice(0,10)+'T12:00:00').toLocaleDateString(language==='es'?'es-US':'en-US',{month:'short',day:'numeric',year:'numeric'});}
function displayAddress(address){
 return String(address??'').toLowerCase().replace(/\b[a-z]+/g,word=>/^(n|s|e|w|ne|nw|se|sw)$/.test(word)?word.toUpperCase():word[0].toUpperCase()+word.slice(1)).replace(/(\d)(St|Nd|Rd|Th)\b/g,(_,digit,suffix)=>digit+suffix.toLowerCase());
}
function known(v,suffix=''){return v===null||v===undefined||v===''?'Not supplied':esc(v)+suffix;}
function badge(label,kind='unknown'){return `<span class="status ${kind}">${esc(label)}</span>`;}
function cityProperties(){return properties.filter(p=>p.city===$('#city').value);}
function sourceRelevant(s,p=selected){return s.jurisdictions===p.state||s.jurisdictions===cities[p.city].name+', '+p.state;}
function readings(p=selected){return D.readings.filter(r=>sourceRelevant(sourcesById[r.doc_id],p)&&enabled.has(r.cat));}
function temporal(r){
 if(r.temporal==='pending')return {label:'Pending at capture',kind:'pending',note:'The captured bill page is pending. Later outcomes have not been checked.'};
 if(r.effective_date&&date()<r.effective_date)return {label:'Before effective period',kind:'future',note:`Recorded start: ${shortDate(r.effective_date)}. Earlier versions are not reconstructed.`};
 if(r.end_date&&date()>r.end_date)return {label:'Outside published period',kind:'none',note:`This published rate ends ${shortDate(r.end_date)}; no later rate is loaded.`};
 if(date()!==D.snapshot&&!r.effective_date)return {label:'History not evaluated',kind:'none',note:'This document was captured on October 1, 2026. Its applicability on other dates has not been reconstructed.'};
 if(date()>D.snapshot)return {label:'Not rechecked',kind:'none',note:`${r.effective_date?'Recorded start: '+shortDate(r.effective_date)+'. ':''}No source update after the October 1 snapshot is connected.`};
 return {label:'Source available',kind:'applies',note:r.effective_date?`Recorded period starts ${shortDate(r.effective_date)}${r.end_date?' and ends '+shortDate(r.end_date):''}.`:'Read from the supplied October 1, 2026 snapshot.'};
}
function building(p=selected){return E.buildings[p.id]||{};}
function legalCity(b){return b.legal_city||(b.legal_city_candidate?b.legal_city_candidate+' (candidate)':'Unresolved');}
function overrideKey(p=selected){const o=factOverrides.get(p.id)||{};return `${o.year_built||''}/${o.units||''}`;}
function resultKey(p=selected,d=date()){return `${p.id}/${d}/${overrideKey(p)}`;}
async function loadDatedResults(p,d){
 const key=resultKey(p,d);if(datedResults.has(key))return;
 datedResults.set(key,{loading:true});
 try{
  const o=factOverrides.get(p.id)||{},params=new URLSearchParams({address:p.id,as_of:d});
  if(o.year_built)params.set('year_built',o.year_built);if(o.units)params.set('units',o.units);
  const response=await fetch(`api/lookup?${params}`,{signal:AbortSignal.timeout(15000)});
  if(!response.ok)throw new Error('unavailable');
  const data=await response.json();
  if(data.address_id!==p.id||data.as_of!==d||data.rules_sha256!==E.rules_sha256||!Array.isArray(data.lookups))throw new Error('mismatched data');
  datedResults.set(key,{entries:data.lookups});
 }catch{datedResults.set(key,{error:true});}
 if(resultKey()===key)renderDetail();
}
function verdicts(p=selected,d=date()){
 const entries=overrideKey(p)==='/'?E.lookups[d]?.[p.id]:null;
 const vs=entries?entries.map(([id,result,t,c])=>({id,result,explanation:E.texts[t],conflict:!!c})):(datedResults.get(resultKey(p,d))?.entries||[]).map(e=>({id:e.team_rule_id,result:e.result,explanation:e.explanation,conflict:!!e.conflict_flag}));
 return vs.map(v=>({...v,rule:E.rules[v.id],detail:d===E.default_date?E.details?.[p.id]?.[v.id]:null})).filter(v=>v.rule).sort((a,b)=>resultOrder.indexOf(a.result)-resultOrder.indexOf(b.result)||a.id.localeCompare(b.id));
}
function publicExplanation(text){return String(text||'').replace(/\br-\d{4}\b/g,id=>E.rules[id]?.title||'another applicable rule');}
function verdictCard(v){
 const r=v.rule,label=v.result==='applies'?(audience==='tenant'?(language==='es'?'Se aplica un derecho o protección':'Right or protection applies'):(language==='es'?'Se aplica una obligación':'Obligation applies')):(tr(v.result)||v.result);
 const review=v.detail?.needs_review?`<p class="review-note">${esc(tr('human_review'))}</p>`:'';
 const summary=v.detail?.summary?`<p class="verdict-summary">${esc(v.detail.summary)}</p>`:'';
 const missing=v.detail?.missing_facts?.length?`<p class="missing-facts">${esc(tr('missing'))}: ${v.detail.missing_facts.map(esc).join(', ')}.</p>`:'';
 const hint=v.result==='unknown'&&v.detail?.fact_hint?`<div class="fact-hint"><strong>${language==='es'?'Dato que puede resolverlo':'Fact that may resolve this'}</strong><br>${esc(v.detail.fact_hint.condition)}</div>`:'';
 const plain=(r.plain_language||{})[language]||(r.plain_language||{}).en;
 const verified=((r.verification||{}).verdicts||{}).citation==='supported';
 const provenance=`<div class="provenance-badges">${verified?`<span class="verified">${language==='es'?'Cita verificada en la fuente':'Citation verified in source'}</span>`:''}${r.source_type==='secondary'?`<span class="secondary">${language==='es'?'Fuente secundaria':'Secondary source'}</span>`:`<span>${language==='es'?'Fuente oficial':'Official source'}</span>`}${r.source_capture?`<span>${language==='es'?'Captura oficial fuera del corpus':'Official capture outside corpus'}</span>`:''}</div>`;
 return `<article class="rule-card engine-rule" data-rule="${esc(v.id)}"><div class="rule-title"><h3>${esc(r.title)}</h3></div><div class="rule-jurisdiction">${esc(r.jurisdiction)}</div><p class="verdict-status">${esc(label)}${v.conflict?(language==='es'?' — conflicto para revisar':' — conflict to review'):''} · ${language==='es'?'A fecha de':'As of'} ${esc(shortDate(date()))}</p>${plain?`<p class="plain-language">${esc(plain)}</p>`:summary}${review}${hint}${r.key_value?`<div class="rule-value">${esc(r.key_value)}</div>`:''}<details class="verdict-evidence"><summary>${esc(tr('why'))}</summary><p>${esc(publicExplanation(v.detail?.reasoning||v.explanation))}</p>${missing}${provenance}<div class="verdict-meta"><span>${esc(r.citation)}</span>${v.detail?.confidence!==undefined&&v.detail?.confidence!==null?`<span>${esc(tr('confidence'))} ${Math.round(v.detail.confidence*100)}%</span>`:''}</div><blockquote>${esc(r.quoted_span)}</blockquote><div class="verdict-meta"><a href="${safeUrl(r.source_url)}" target="_blank" rel="noopener">${esc(tr('open_source'))} ${icon('external')}</a><span>${esc(tr('retrieved'))} ${esc(r.retrieved_at||'date not recorded')}</span>${r.effective_date?`<span>${esc(tr('effective'))} ${esc(r.effective_date)}</span>`:''}</div></details></article>`;
}
function verdictGroups(vs){
 const summary=resultOrder.map(result=>[result,vs.filter(v=>v.result===result).length]).filter(([,n])=>n).map(([result,n])=>`${n} ${tr(result)||result}`).join(' · ');
 const section=(items,title,note)=>{
  if(!items.length)return '';
  const groups=categories.map(([cat])=>[cat,items.filter(v=>catOf[v.rule.category]===cat)]).filter(([,rows])=>rows.length);
  return `<section class="rule-section"><div class="rule-section-heading"><h3>${esc(title)}</h3><span>${items.length}</span></div>${note?`<p class="rule-section-note">${esc(note)}</p>`:''}${groups.map(([cat,rows])=>`<div class="rule-category"><div class="rule-category-heading"><strong>${esc(categoryLabel()[cat])}</strong><span>${rows.length}</span></div>${rows.map(verdictCard).join('')}</div>`).join('')}</section>`;
 };
 const ordinary=vs.filter(v=>!v.rule.event_only&&!v.rule.subsidized_program);
 const programs=vs.filter(v=>!v.rule.event_only&&v.rule.subsidized_program);
 const events=vs.filter(v=>v.rule.event_only);
 const audienceIntro=audience==='tenant'?(language==='es'?'Tus derechos y protecciones según las reglas coincidentes.':'Your rights and protections under the matching rules.'):(language==='es'?'Tus obligaciones y controles de cumplimiento según las reglas coincidentes.':'Your obligations and compliance checks under the matching rules.');
 const ordinaryTitle=audience==='tenant'?(language==='es'?'Derechos y protecciones':'Rights and protections'):(language==='es'?'Deberes y restricciones':'Duties and restrictions');
 return `<div class="audience-switch" role="group" aria-label="Choose legal perspective"><button data-audience="tenant" aria-pressed="${audience==='tenant'}">${language==='es'?'Inquilino · tus derechos':'Tenant · your rights'}</button><button data-audience="landlord" aria-pressed="${audience==='landlord'}">${language==='es'?'Propietario · tus obligaciones':'Landlord · your obligations'}</button></div><p class="audience-intro">${audienceIntro}</p><div class="verdict-summary"><strong>${vs.length} ${language==='es'?'reglas coincidentes':'matching rules'}</strong><small>${esc(summary||(language==='es'?'Sin resultado actual':'No current result'))} · ${language==='es'?'A fecha de':'As of'} ${esc(shortDate(date()))}</small></div>${section(ordinary,ordinaryTitle,'')}${section(programs,language==='es'?'Programas asequibles y subvencionados':'Subsidized and affordable programs',language==='es'?'Estas reglas dependen de un programa o restricción de asequibilidad registrado.':'These rules are limited to a recorded subsidy, affordability restriction, or named housing program.')}${section(events,language==='es'?'Reglas activadas por eventos':'Event-triggered rules',language==='es'?'Solo importan cuando ocurre el evento indicado.':'These rules matter only when the stated event occurs.')}`;
}
function nextChangePanel(p){
 const n=(E.scheduled_changes?.[p.id]||[]).find(step=>step.date>date());
 if(!n)return '<p class="fact-note">No later scheduled result change through 2028.</p>';
 const count=n.changes?.length||0;
 return `<p class="next-change"><strong>Next result change: ${esc(shortDate(n.date))}</strong><span>${count} rule${count===1?'':'s'} change${count===1?'s':''} status.</span></p>`;
}
function renderLayers(){
 $('#category-layers').innerHTML=categories.map(([id,label,color])=>`<label class="layer-row"><span class="layer-icon ${color}">${icon(id)}</span><span>${esc(label[language])}</span><input type="checkbox" data-category="${id}" ${enabled.has(id)?'checked':''} aria-label="${language==='es'?'Mostrar':'Show'} ${esc(label[language])}"><span class="switch"></span></label>`).join('');
}
function renderProperties(){
 const ps=cityProperties();$('#property-count').textContent=ps.length;
 $('#properties-pane').innerHTML=`<div class="list-note">Dataset city group · legal city shown per property</div>`+ps.map(p=>`<button class="property-list-item ${p.id===selected.id?'selected':''}" data-property="${p.id}"><strong>${esc(p.address)}</strong><small>${p.id} · ${p.units===null?'Units not supplied':p.units+' units'} · ${p.year||'Year unknown'}</small>${badge(p.coord?(p.geocode.match_type==='Exact'?'Address matched':'Match needs review'):'No address match',p.coord&&p.geocode.match_type==='Exact'?'applies':'unknown')}</button>`).join('');
}
function renderMarkers(){
 markers.forEach(m=>m.remove());markers=[];renderProperties();
 if(!map||!$('#property-layer').checked)return;
 const plotted=changeOverlay?properties.filter(p=>changeOverlay.ids.has(p.id)):cityProperties();
 plotted.filter(p=>p.coord).forEach(p=>{
  const overlayClass=changeOverlay?(changeOverlay.kind==='conflict_flag_address_ids'?'conflict':'affected'):'';
  const el=document.createElement('button');el.className=`pin ${p.geocode.match_type==='Exact'?'':'unknown'} ${overlayClass} ${p.id===selected.id?'selected':''}`;
  el.innerHTML=`${icon('building')}${p.units===null?'?':p.units}`;
  el.setAttribute('aria-label',`Open ${p.address}, record ${p.id}`);
  el.addEventListener('click',()=>chooseProperty(p.id));
  markers.push(new maplibregl.Marker({element:el,anchor:'bottom'}).setLngLat(p.coord).addTo(map));
 });
}
function ruleCard(r){
 const t=temporal(r);
 return `<article class="rule-card"><div class="rule-title"><h3>${esc(r.title)}</h3></div><div class="rule-jurisdiction">${esc(r.jurisdiction)}</div>${['Pending at capture','Before effective period','Outside published period'].includes(t.label)?`<p class="rule-date-status">${esc(t.label)} · ${esc(t.note)}</p>`:''}<div class="rule-value">${esc(r.value)}</div><p>${esc(r.summary)}</p><button class="source-link" data-reading="${r.id}">Read source ${icon('chevron')}</button></article>`;
}
function factsPanel(p){
 const b=building(p);
 const pairs=[['Legal city',legalCity(b)],['City status',b.city_status],['County',b.county],['Year built',p.year],['Units',p.units],['Property type',p.use_description],['Use code',p.use_code],['Postal city',p.postal_city],['ZIP code',p.zip]];
 const o=factOverrides.get(p.id)||{};
 const editor=`<form class="fact-editor" id="fact-editor"><h3>${language==='es'?'Probar datos faltantes':'Test missing facts'}</h3><p>${language==='es'?'Estos valores son hipotéticos y no modifican el registro oficial.':'These values are hypothetical and never alter the official record.'}</p><div class="fact-editor-fields"><label>${language==='es'?'Año de construcción':'Year built'}<input name="year_built" type="number" min="1600" max="${new Date().getFullYear()}" value="${esc(o.year_built||'')}" placeholder="${esc(p.year||'e.g. 1978')}"></label><label>${language==='es'?'Número de viviendas':'Number of units'}<input name="units" type="number" min="1" max="100000" value="${esc(o.units||'')}" placeholder="${esc(p.units||'e.g. 5')}"></label></div><div class="fact-editor-actions"><button class="primary-button" type="submit">${language==='es'?'Recalcular':'Recalculate'}</button>${overrideKey(p)!=='/'?`<button class="text-button" type="button" data-clear-facts>${language==='es'?'Restablecer':'Reset'}</button>`:''}</div></form>`;
 return `${editor}<dl class="building-facts">${pairs.map(([k,v])=>`<div><dt>${esc(k)}</dt><dd>${v===null||v===undefined||v===''?'—':esc(v)}</dd></div>`).join('')}</dl>${b.missing_facts?.length?`<p class="missing-facts">${esc(tr('missing'))}: ${b.missing_facts.map(esc).join(', ')}.</p>`:''}${b.flags?.length?`<p class="fact-note">Flags: ${b.flags.map(esc).join(', ')}</p>`:''}<details class="fact-source"><summary>Source details</summary><p>${esc(p.source_dataset)}</p><p>Record ${esc(p.id)} · Retrieved ${esc(p.retrieved_at)}</p><a href="data/sample_addresses.csv" download>Download CSV</a></details>`;
}
function timelinePanel(p){
 const rs=readings(p).filter(r=>r.effective_date||r.temporal==='pending').sort((a,b)=>(b.effective_date||'').localeCompare(a.effective_date||''));
 return `<p class="timeline-snapshot">Source snapshot · ${shortDate(D.snapshot)}</p>${rs.length?rs.map(r=>`<div class="timeline-item"><small>${r.temporal==='pending'?'Pending at capture':shortDate(r.effective_date)+(r.end_date?' – '+shortDate(r.end_date):'')}</small><h3>${esc(r.title)}</h3><button class="source-link" data-reading="${r.id}">Read source ${icon('chevron')}</button></div>`).join(''):'<p class="fact-note">No dated changes available.</p>'}`;
}
function renderDetail(){
 const p=selected,rs=readings(),b=building(p);
 $('#today').hidden=date()===localToday();
 const hasStatic=overrideKey(p)==='/'&&E.lookups[date()]?.[p.id];
 if(!hasStatic)loadDatedResults(p,date());
 const lookup=datedResults.get(resultKey());
 const dateMessage=!hasStatic?(lookup?.error?(language==='es'?'El recálculo no está disponible en este alojamiento estático.':'Recalculation is unavailable on this static host.'):lookup?.loading?(language==='es'?'Calculando reglas…':'Loading rules…'):''):'';
 const vs=verdicts(p).filter(v=>enabled.has(catOf[v.rule.category]));
 $('#detail').innerHTML=`<div class="detail-top"><div class="property-heading"><h2 class="address-title">${esc(displayAddress(p.address))}</h2><div class="detail-actions"><button class="icon-button" id="save-property" aria-label="${saved.has(p.id)?'Unsave':'Save'} property">${icon(saved.has(p.id)?'check':'bookmark')}</button><button class="icon-button" id="close-detail" aria-label="Close property profile">${icon('close')}</button></div></div><p class="address-sub">${esc(p.id)} · Legal city: ${esc(legalCity(b))} · <span title="city_status">${esc(b.city_status||'unknown')}</span>${overrideKey(p)!=='/'?` · <strong>${language==='es'?'Hipótesis del usuario':'User-supplied hypothetical'}</strong>`:''}</p></div><div class="detail-tabs" role="tablist" aria-label="Property information"><button data-detail="rules" role="tab" aria-selected="${detailTab==='rules'}" class="${detailTab==='rules'?'active':''}">${esc(tr('rules'))} <span class="count">${vs.length}</span></button><button data-detail="facts" role="tab" aria-selected="${detailTab==='facts'}" class="${detailTab==='facts'?'active':''}">${esc(tr('facts'))}</button><button data-detail="timeline" role="tab" aria-selected="${detailTab==='timeline'}" class="${detailTab==='timeline'?'active':''}">${esc(tr('previews'))}</button></div><div class="detail-scroll">${detailTab==='rules'?`${nextChangePanel(p)}${dateMessage?`<div class="empty" role="status">${dateMessage}</div>`:verdictGroups(vs)}${dateMessage?'':enabled.size===0?'<div class="empty">Select a topic to see its rules.</div>':vs.length?'':'<div class="empty">No rule matches this property for the selected topics.</div>'}`:detailTab==='facts'?factsPanel(p):`<p class="fact-note">Curated source previews (manual readings, not engine output).</p>${rs.map(ruleCard).join('')||'<p class="fact-note">No preview for this group.</p>'}${timelinePanel(p)}`}</div>`;
}
function mapPadding(){if(innerWidth<=650)return{bottom:Math.max(0,map.getContainer().clientHeight-300),top:70,left:0,right:0};const d=$('#detail');return{right:d.hidden?0:Math.max(0,map.getContainer().getBoundingClientRect().right-d.getBoundingClientRect().left),left:0,top:0,bottom:0};}
function focusMap(center,zoom=13){if(map)map.easeTo({center,zoom,padding:mapPadding(),offset:[0,15],duration:matchMedia('(prefers-reduced-motion: reduce)').matches?0:500});}
function fitMap(){
 if(!map)return;
 const ps=cityProperties().filter(p=>p.coord);
 if(ps.length){const bounds=new maplibregl.LngLatBounds();ps.forEach(p=>bounds.extend(p.coord));const padding=mapPadding();map.fitBounds(bounds,{padding:{top:110,bottom:125,left:45,right:padding.right+35},maxZoom:13,duration:500});}
 else focusMap(cities[$('#city').value].center,cities[$('#city').value].zoom);
}
function chooseProperty(id){
 const p=properties.find(p=>p.id===id);if(!p)return;selected=p;$('#city').value=p.city;syncCityPicker();$('#city-pill').textContent=cities[p.city].name;detailTab='rules';setView('explore');$('#detail').hidden=false;$('#reopen').hidden=true;$('.map-workspace').classList.remove('profile-closed');$('#search-results').hidden=true;$('#search').value='';renderDetail();renderMarkers();focusMap(p.coord||cities[p.city].center,p.coord?13:cities[p.city].zoom);if(!p.coord)toast('No address match. Map shows the city area, not this property.');
}
function openModal(label,html,style=''){const modal=$('#modal');modal.className=style;modal.removeAttribute('aria-labelledby');$('#modal-eyebrow').textContent=label;$('#modal-body').innerHTML=html;if(style==='reading-dialog')modal.setAttribute('aria-labelledby','reading-title');modal.showModal();}
function showReading(id){
 const r=D.readings.find(r=>r.id===id);if(!r)return;const s=sourcesById[r.doc_id];
 openModal('',`<header class="reading-header"><h2 id="reading-title">${esc(r.title)}</h2><div class="reading-publisher"><span>${esc(s.jurisdictions)}</span><span>${esc(sourceHost(s))}</span></div></header><div class="reading-scroll"><div class="reading-excerpt-label">Source excerpt</div><blockquote class="reading-excerpt">${esc(r.quote)}</blockquote><details class="reading-details"><summary>Details</summary><dl><div><dt>Captured</dt><dd>${shortDate(s.retrieved_at||D.snapshot)}</dd></div><div><dt>Document</dt><dd>${esc(r.doc_id)}</dd></div></dl><h3>Applicability to this property</h3><p>${esc(r.needs)}</p><p>${esc(temporal(r).note)}</p></details></div><footer class="reading-footer"><a href="${safeUrl(s.url)}" target="_blank" rel="noopener">Open original source ${icon('external')}</a>${s.local_path?`<a href="${esc(s.local_path)}" target="_blank" rel="noopener">Full text ${icon('chevron')}</a>`:''}</footer>`,'reading-dialog');
}
function sourceTitle(s){
 const reading=D.readings.find(r=>r.doc_id===s.doc_id);
 if(reading)return reading.title;
 const firstLine=s.text?.split('\n').slice(3).find(line=>line.trim())?.trim();
 if(firstLine&&firstLine.length>8&&firstLine.length<160&&!/^(?:\d|Page |Department |The Department |Ch\. |MOTION$|Human Rights Commission \|)/i.test(firstLine))return firstLine.replace(/\s+(?:\||–)\s+[^|]+$/,'');
 try{
  const url=new URL(s.url),name=decodeURIComponent(url.pathname.split('/').filter(Boolean).pop()||'').replace(/\.(pdf|html?|aspx?)$/i,'').replace(/[-_]+/g,' ').trim();
  if(!name||/^(?:view|download|\d[\d-]*)$/i.test(name))return `Document ${s.doc_id}`;
  return name[0].toUpperCase()+name.slice(1);
 }catch{return `Document ${s.doc_id}`;}
}
function sourceHost(s){try{return new URL(s.url).hostname.replace(/^www\./,'');}catch{return '';}}
function showSource(id){
 const s=sourcesById[id];if(!s)return;
 const text=s.text?s.text.split('\n').slice(3).join('\n').trim():'';
 const excerpt=text.slice(0,1600);
 openModal('SOURCE',`<h2>${esc(sourceTitle(s))}</h2><div class="source-document-meta"><span>${esc(s.jurisdictions)}</span><span>${esc(sourceHost(s))}</span></div>${s.retrieved_at?`<p class="source-captured">Captured ${shortDate(s.retrieved_at)}</p>`:''}${excerpt?`<blockquote class="exact-quote source-document-quote">${esc(excerpt)}${text.length>1600?'…':''}</blockquote><p><a href="${esc(s.local_path)}" target="_blank" rel="noopener">Read full text</a></p>`:'<p>No local text available.</p>'}<p><a href="${safeUrl(s.url)}" target="_blank" rel="noopener">Open original source</a></p>`);
}
function scopeFor(test){
 if(test.test_id==='T2')return properties.filter(p=>['jc','hoboken'].includes(p.city));
 if(test.test_id==='T5')return [];
 return properties.filter(p=>test.states?.includes(p.state));
}
const changeDescriptions={
 T1:{title:'California AB 325 / SB 763',summary:'Compare the algorithmic-pricing rules before and after the effective date.'},
 T2:{title:'Hoboken and Jersey City algorithmic bans',summary:'Separate local rules for each city. Newark is excluded.'},
 T3:{title:'New Jersey FAIR Act',summary:'Compare the effective-date transition and review conflicts with Hoboken and Jersey City rules.'},
 T4:{title:'Massachusetts S.2983 and H.5222',summary:'Pending bills. Boston and Cambridge properties would need review if enacted.'},
 T5:{title:'Massachusetts rent-control ballot question',summary:'The failed proposal creates no rent cap in this scenario.'}
};
function changeIds(t,kind){return E.changes[t]?.[kind]||[];}
function renderChanges(){
 return `<div class="collection-top changes-top"><h2>Law changes</h2><button class="icon-button" data-return aria-label="Return to map">${icon('close')}</button></div><div class="changes-list">${D.change_tests.map(t=>{
  const copy=changeDescriptions[t.test_id]||{title:t.title,summary:t.expected_behavior},aff=changeIds(t.test_id,'affected_address_ids'),con=changeIds(t.test_id,'conflict_flag_address_ids');
  const status=t.type==='pending'?'Pending proposal':t.type==='negative'?'Failed proposal':t.type==='boundary'?'Local scope':'Date comparison';
  const dates=t.as_of_before?`${shortDate(t.as_of_before)} → ${shortDate(t.as_of_after)}`:`As of ${shortDate(t.as_of)}`;
  return `<article class="change-row"><div class="change-row-meta"><span>${status}</span><span>${dates}</span></div><div class="change-row-heading"><h3>${esc(t.test_id)} · ${esc(copy.title)}</h3>${aff.length?`<button class="change-properties" data-test="${t.test_id}" data-kind="affected_address_ids">Review ${aff.length} affected ${icon('chevron')}</button>`:'<span class="change-no-properties">No affected properties</span>'}</div><p>${esc(copy.summary)}</p><div class="change-stats"><div><strong>${aff.length}</strong><span>affected</span></div><div><strong>${con.length}</strong><span>conflict flags</span></div></div>${con.length?`<button class="change-properties" data-test="${t.test_id}" data-kind="conflict_flag_address_ids">Review ${con.length} conflict addresses ${icon('chevron')}</button>`:''}<p class="change-notes">${esc(E.changes[t.test_id]?.notes||'')}</p></article>`;
 }).join('')}</div>`;
}
function renderLibrary(){
 const ss=sourceFilter==='all'?D.sources:D.sources.filter(s=>sourceRelevant(s));
 return `<div class="collection-top library-top"><h2>Source library</h2><button class="icon-button" data-return aria-label="Return to map">${icon('close')}</button></div><div class="library-filter"><select id="source-filter" aria-label="Filter sources"><option value="all" ${sourceFilter==='all'?'selected':''}>All sources</option><option value="property" ${sourceFilter==='property'?'selected':''}>${esc(cities[selected.city].name)} and ${esc(selected.state)}</option></select></div><div class="library-list">${ss.map(s=>`<article class="library-source"><div><h3>${esc(sourceTitle(s))}</h3><div class="library-source-meta"><span>${esc(s.jurisdictions)}</span><span>${esc(sourceHost(s))}</span></div></div>${s.text_available?`<button class="library-read" data-document="${s.doc_id}">Read text ${icon('chevron')}</button>`:`<a class="library-read" href="${safeUrl(s.url)}" target="_blank" rel="noopener">Open source ${icon('external')}</a>`}</article>`).join('')}</div>`;
}
function renderCollection(){if(view!=='explore')$('#collection').innerHTML=view==='changes'?renderChanges():renderLibrary();}
function setView(v){view=v;document.querySelectorAll('[data-view]').forEach(b=>{b.classList.toggle('active',b.dataset.view===v);b.setAttribute('aria-current',b.dataset.view===v?'page':'false');});$('#collection').hidden=v==='explore';renderCollection();}
function setSidebar(v){document.querySelectorAll('[data-side]').forEach(b=>b.setAttribute('aria-selected',b.dataset.side===v));$('#layers-pane').hidden=v!=='layers';$('#properties-pane').hidden=v!=='properties';}
function toast(text){$('#toast').textContent=text;$('#toast').hidden=false;clearTimeout(toast.timer);toast.timer=setTimeout(()=>$('#toast').hidden=true,4000);}
function refresh(){renderDetail();renderMarkers();renderCollection();}
function applyLanguage(){
 document.documentElement.lang=language;$('#language').value=language;
 document.querySelectorAll('[data-i18n]').forEach(el=>el.textContent=tr(el.dataset.i18n));
 renderLayers();refresh();
}
$('#city').innerHTML=Object.entries(cities).map(([key,c])=>`<option value="${key}">${c.name}, ${c.state}</option>`).join('');$('#city').value=selected.city;syncCityPicker();
hydrate();applyLanguage();renderProperties();
try{
 map=new maplibregl.Map({container:'map',center:cities.sf.center,zoom:11.7,attributionControl:false,style:'https://tiles.openfreemap.org/styles/positron'});
 map.addControl(new maplibregl.NavigationControl({showCompass:false}),'top-right');map.addControl(new maplibregl.AttributionControl({compact:false,customAttribution:'Locations: US Census Geocoder'}),'bottom-right');map.on('load',()=>{renderMarkers();fitMap();});map.on('error',()=>{$('#map-error').hidden=false;});map.on('idle',()=>{$('#map-error').hidden=true;});
}catch(e){$('#map-error').hidden=false;console.warn('Map unavailable:',e.message);}
document.addEventListener('click',e=>{
 const b=e.target.closest('button');if(!b)return;
 if(b.dataset.view)setView(b.dataset.view);
 if(b.dataset.side)setSidebar(b.dataset.side);
 if(b.dataset.property)chooseProperty(b.dataset.property);
 if(b.dataset.detail){detailTab=b.dataset.detail;renderDetail();}
 if(b.dataset.audience){audience=b.dataset.audience;renderDetail();}
 if(b.dataset.reading)showReading(b.dataset.reading);
 if(b.dataset.document)showSource(b.dataset.document);
 if(b.hasAttribute('data-open-library')){sourceFilter='property';setView('sources');}
 if(b.hasAttribute('data-return'))setView('explore');
 if(b.dataset.test){const t=D.change_tests.find(t=>t.test_id===b.dataset.test);showCandidates(t,b.dataset.kind);}
 if(b.id==='close-detail'){$('#detail').hidden=true;$('#reopen').hidden=false;$('.map-workspace').classList.add('profile-closed');fitMap();}
 if(b.id==='reopen'){$('#detail').hidden=false;$('#reopen').hidden=true;$('.map-workspace').classList.remove('profile-closed');focusMap(selected.coord||cities[selected.city].center);}
 if(b.id==='save-property'){saved.has(selected.id)?saved.delete(selected.id):saved.add(selected.id);renderDetail();toast(saved.has(selected.id)?'Saved for this session':'Removed from saved');}
 if(b.hasAttribute('data-clear-facts')){factOverrides.delete(selected.id);[...datedResults.keys()].filter(k=>k.startsWith(selected.id+'/')).forEach(k=>datedResults.delete(k));renderDetail();toast(language==='es'?'Hipótesis eliminada':'Hypothetical facts cleared');}
});
document.addEventListener('submit',e=>{
 if(e.target.id!=='fact-editor')return;e.preventDefault();
 const form=new FormData(e.target),year=Number(form.get('year_built')),units=Number(form.get('units')),o={};
 if(year)o.year_built=year;if(units)o.units=units;
 if(!Object.keys(o).length){toast(language==='es'?'Introduce al menos un dato':'Enter at least one fact');return;}
 factOverrides.set(selected.id,o);detailTab='rules';loadDatedResults(selected,date());renderDetail();
});
function showCandidates(t,kind='affected_address_ids'){const ps=changeIds(t.test_id,kind).map(id=>properties.find(p=>p.id===id)).filter(Boolean);if(E.dates.includes(t.as_of_after))$('#as-of').value=t.as_of_after;openModal(kind==='conflict_flag_address_ids'?'CONFLICT ADDRESSES':'AFFECTED PROPERTIES',`<h2>${esc(t.test_id)} · ${esc((changeDescriptions[t.test_id]||t).title)}</h2><p>${ps.length} addresses from the engine change test.</p>${ps.some(p=>p.coord)?`<button class="primary-button" data-map-change="${esc(t.test_id)}" data-map-kind="${esc(kind)}">${language==='es'?'Mostrar todas en el mapa':'Show all on map'}</button>`:''}<div class="candidate-list">${ps.map(p=>`<button class="search-result" data-candidate="${p.id}"><strong>${esc(displayAddress(p.address))}</strong><small>${esc(p.postal_city)}, ${p.state}</small></button>`).join('')}</div>`);}
$('#modal-body').addEventListener('click',e=>{const b=e.target.closest('[data-candidate]');if(b){$('#modal').close();chooseProperty(b.dataset.candidate);setSidebar('properties');}});
$('#modal-body').addEventListener('click',e=>{const b=e.target.closest('[data-map-change]');if(!b)return;const ids=new Set(changeIds(b.dataset.mapChange,b.dataset.mapKind));changeOverlay={ids,kind:b.dataset.mapKind,test:b.dataset.mapChange};$('#modal').close();setView('explore');renderMarkers();const ps=properties.filter(p=>ids.has(p.id)&&p.coord);if(map&&ps.length){const bounds=new maplibregl.LngLatBounds();ps.forEach(p=>bounds.extend(p.coord));map.fitBounds(bounds,{padding:70,maxZoom:12,duration:500});}toast(`${b.dataset.mapChange}: ${ids.size} ${language==='es'?'direcciones en el mapa':'addresses on map'}`);});
$('#city').addEventListener('change',()=>{chooseProperty(cityProperties()[0].id);fitMap();});
$('#category-layers').addEventListener('change',e=>{const cat=e.target.dataset.category;if(cat){e.target.checked?enabled.add(cat):enabled.delete(cat);renderDetail();}});
$('#property-layer').addEventListener('change',renderMarkers);
function updateDate(){if(!$('#as-of').value)$('#as-of').value=localToday();refresh();}
$('#as-of').addEventListener('change',updateDate);
$('#language').value=language;
$('#language').addEventListener('change',()=>{language=$('#language').value==='es'?'es':'en';localStorage.setItem('parcel-language',language);applyLanguage();document.dispatchEvent(new CustomEvent('parcel-language-change',{detail:{language}}));});
$('#today').addEventListener('click',()=>{$('#as-of').value=localToday();updateDate();});
window.addEventListener('pageshow',event=>{if(event.persisted){$('#as-of').value=E.default_date||localToday();updateDate();}});
$('#search').addEventListener('input',()=>{
 const q=$('#search').value.trim().toLowerCase();if(!q){$('#search-results').hidden=true;return;}
 const ps=properties.filter(p=>`${p.id} ${p.address} ${p.postal_city} ${cities[p.city].name}`.toLowerCase().includes(q));
 $('#search-results').innerHTML=ps.length?`<div class="list-note">${ps.length} matches${ps.length>100?' · First 100 shown; refine your search':''}</div>`+ps.slice(0,100).map(p=>`<button class="search-result" data-property="${p.id}"><strong>${esc(p.address)}</strong><small>${p.id} · ${esc(p.postal_city)}, ${p.state}${p.coord?'':' · No map match'}</small></button>`).join(''):'<div class="empty">No supplied record matches. Try a city, street, or an ID such as A0016.</div>';
 $('#search-results').hidden=false;
});
$('#search').addEventListener('keydown',e=>{if(e.key==='Enter')$('#search-results [data-property]')?.click();if(e.key==='Escape')$('#search-results').hidden=true;});
document.addEventListener('click',e=>{if(!e.target.closest('.search-wrap'))$('#search-results').hidden=true;});
document.addEventListener('keydown',e=>{if(e.key==='/'&&!['INPUT','TEXTAREA','SELECT'].includes(document.activeElement.tagName)&&!$('#modal').open){e.preventDefault();$('#chat-input').focus();}});
$('#collection').addEventListener('change',e=>{if(e.target.id==='source-filter'){sourceFilter=e.target.value;renderCollection();}});
$('#close-modal').addEventListener('click',()=>$('#modal').close());$('#modal').addEventListener('click',e=>{if(e.target===$('#modal')){const r=$('#modal').getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)$('#modal').close();}});
let resizeTimer;window.addEventListener('resize',()=>{clearTimeout(resizeTimer);resizeTimer=setTimeout(()=>{if(map){map.resize();focusMap(selected.coord||cities[selected.city].center,map.getZoom());}},150);});

const cityStates={CA:'California',MA:'Massachusetts',NJ:'New Jersey'};
let cityMatches=[],cityActive=-1;
function syncCityPicker(){
 const c=cities[$('#city').value];
 $('#city-current-name').textContent=c.name;
 $('#city-current-state').textContent=c.state;
 $('#city-trigger').setAttribute('aria-label',`Choose a city: ${c.name}, ${c.state}`);
}
function renderCityOptions(){
 const query=$('#city-search').value.trim().toLowerCase();
 cityMatches=Object.entries(cities).filter(([,c])=>`${c.name} ${c.state} ${cityStates[c.state]}`.toLowerCase().includes(query)).sort((a,b)=>cityStates[a[1].state].localeCompare(cityStates[b[1].state])||a[1].name.localeCompare(b[1].name));
 cityActive=Math.max(0,cityMatches.findIndex(([id])=>id===$('#city').value));
 $('#city-options').innerHTML=Object.entries(cityStates).map(([state,name])=>{
  const matches=cityMatches.filter(([,c])=>c.state===state);
  return matches.length?`<div role="group" aria-label="${name}"><div class="city-group-label" aria-hidden="true">${name}</div>${matches.map(([id,c])=>`<button id="city-option-${id}" class="city-option" role="option" tabindex="-1" aria-selected="${id===$('#city').value}" data-city="${id}"><span>${esc(c.name)}</span>${id===$('#city').value?icon('check'):''}</button>`).join('')}</div>`:'';
 }).join('');
 $('#city-empty').hidden=cityMatches.length>0;
 highlightCity();
}
function highlightCity(){
 document.querySelectorAll('.city-option').forEach(option=>option.classList.toggle('keyboard-active',option.dataset.city===cityMatches[cityActive]?.[0]));
 const id=cityMatches[cityActive]?.[0];
 if(id){$('#city-search').setAttribute('aria-activedescendant','city-option-'+id);$('#city-option-'+id)?.scrollIntoView({block:'nearest'});}
 else $('#city-search').removeAttribute('aria-activedescendant');
}
function closeCityPicker(restoreFocus=false){
 if($('#city-menu').matches(':popover-open'))$('#city-menu').hidePopover();
 if(restoreFocus)$('#city-trigger').focus();
}
function chooseCity(id){
 if(!cities[id])return;
 changeOverlay=null;
 $('#city').value=id;
 $('#city').dispatchEvent(new Event('change'));
 closeCityPicker(true);
}
$('#city-trigger').addEventListener('click',()=>{
 const menu=$('#city-menu');
 if(menu.matches(':popover-open')){closeCityPicker();return;}
 const rect=$('#city-trigger').getBoundingClientRect(),width=Math.min(Math.max(rect.width,280),innerWidth-24);
 menu.style.width=width+'px';menu.style.left=Math.min(rect.left,innerWidth-width-12)+'px';
 const roomBelow=innerHeight-rect.bottom-20,height=Math.min(424,innerHeight-24);
 menu.style.top=(roomBelow>=Math.min(height,250)?rect.bottom+8:Math.max(12,rect.top-height-8))+'px';
 menu.style.maxHeight=(roomBelow>=Math.min(height,250)?Math.min(height,roomBelow):height)+'px';
 $('#city-search').value='';menu.showPopover();renderCityOptions();$('#city-search').focus();
});
$('#city-menu').addEventListener('toggle',e=>$('#city-trigger').setAttribute('aria-expanded',String(e.newState==='open')));
$('#city-search').addEventListener('input',renderCityOptions);
$('#city-options').addEventListener('click',e=>{const option=e.target.closest('[data-city]');if(option)chooseCity(option.dataset.city);});
$('#city-search').addEventListener('keydown',e=>{
 if(e.key==='ArrowDown'||e.key==='ArrowUp'){e.preventDefault();if(!cityMatches.length)return;cityActive=(cityActive+(e.key==='ArrowDown'?1:-1)+cityMatches.length)%cityMatches.length;highlightCity();}
 if(e.key==='Home'||e.key==='End'){if(!cityMatches.length)return;e.preventDefault();cityActive=e.key==='Home'?0:cityMatches.length-1;highlightCity();}
 if(e.key==='Enter'){e.preventDefault();if(cityMatches[cityActive])chooseCity(cityMatches[cityActive][0]);}
 if(e.key==='Escape'){e.preventDefault();e.stopPropagation();closeCityPicker(true);}
 if(e.key==='Tab')closeCityPicker();
});
window.addEventListener('resize',()=>closeCityPicker());
function renderBuildInfo(v={}){
 const part=(value,length)=>value?esc(String(value).slice(0,length)):'local';
 $('#build-info').innerHTML=`Build ${part(v.git_sha,7)} · rules ${part(v.rules_sha256,12)} · ${part(v.generated_at,10)}`;
}
renderBuildInfo(E.version||{rules_sha256:E.rules_sha256});
fetch('api/version',{signal:AbortSignal.timeout(5000)}).then(r=>r.ok?r.json():null).then(v=>{if(v&&typeof v==='object')renderBuildInfo(v);}).catch(()=>{});
