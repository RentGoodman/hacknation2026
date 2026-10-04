(function(){
 const root=$('#map-chat'),panel=$('#chat-panel'),log=$('#chat-log'),input=$('#chat-input'),send=$('#chat-send');
 const history=[];let busy=false,actions=[],citations=[];
 const picker=$('#chat-address-picker'),addressSearch=$('#chat-address-search');
 let mentionRange=null,addressMatches=[],addressActive=0,lastAddress=selected.id;
 window.ParcelChatProvider={async reply({message,context,history,signal}){
  const response=await fetch('api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message,address_id:context.property.id,as_of:context.asOf,language,history:history.slice(-6)}),signal});
  const data=await response.json();if(!response.ok)throw new Error(data.error||'The answer could not load.');
  if(data.address_id!==context.property.id||data.as_of!==context.asOf)throw new Error('The answer context did not match.');
  return data;
 }};
 function context(){
  const p=selected,d=date();
  return {property:p,building:building(p),cityName:cities[p.city].name,asOf:d,verdicts:verdicts(p,d),available:!!E.lookups[d]?.[p.id]||!!datedResults.get(resultKey(p,d))?.entries,tests:D.change_tests,changes:E.changes,properties};
 }
 function sync(){
  const p=selected;
  $('#chat-address-label').textContent=displayAddress(p.address);
  $('#chat-address-tag').setAttribute('aria-label',`Chat address: ${displayAddress(p.address)}, ${cities[p.city].name}. Change address`);
  $('#chat-address-tag').title=`${p.id} — ${displayAddress(p.address)}, ${cities[p.city].name}`;
  if(lastAddress!==p.id){hideAddressPicker();lastAddress=p.id;}
  $('#chat-context').textContent=`${displayAddress(p.address)} / ${date()}`;
  $('#chat-mode').textContent=language==='es'?'Parcel · Español':'Parcel';
  root.hidden=view!=='explore';
 }
 function open(){sync();panel.hidden=false;$('#chat-resume').hidden=true;input.setAttribute('aria-expanded','true');}
 function close(){panel.hidden=true;$('#chat-resume').hidden=!history.length;input.setAttribute('aria-expanded','false');}
 function actionButton(a){
  const index=actions.push(a)-1;
  return `<button type="button" data-chat-action="${index}">${esc(a.label)} ${icon('chevron')}</button>`;
 }
 function citationButton(source,label){const index=citations.push(source)-1;return `<button type="button" class="chat-citation" data-chat-citation="${index}" aria-label="Read source ${source.id}">${esc(label)}</button>`;}
 function answerText(answer){return esc(answer.text).replace(/\[(\d+)\]/g,(match,id)=>{const source=answer.sources?.find(s=>s.id===Number(id));return source?citationButton(source,match):match;});}
 function sourceLinks(answer){return answer.sources?.length?`<div class="chat-sources">${answer.sources.map(s=>citationButton(s,`[${s.id}] ${sourceHost(sourcesById[s.docId])}`)).join('')}</div>`:'';}
 function showCitation(ref){
  if(!ref)return;const source=sourcesById[ref.docId];if(!source)return;
  openModal('',`<header class="reading-header"><h2 id="reading-title">${esc(sourceTitle(source))}</h2><div class="reading-publisher">${esc(sourceHost(source))}</div></header><div class="reading-scroll"><div class="reading-excerpt-label">Cited passage</div><blockquote class="reading-excerpt">${esc(ref.quote)}</blockquote></div><footer class="reading-footer"><a href="${safeUrl(source.url)}" target="_blank" rel="noopener">Open original source ${icon('external')}</a></footer>`,'reading-dialog');
 }
 function render(){
  actions=[];citations=[];
  log.innerHTML=history.map(m=>`<article class="chat-turn"><p class="chat-question">${esc(m.question)}</p><small class="chat-answer-context">${esc(m.address)} / ${esc(m.asOf)}</small>${m.answer?`<p class="chat-answer">${answerText(m.answer)}</p>${(m.answer.items||[]).map(item=>`<div class="chat-result"><h3>${esc(item.title)}</h3>${item.text?`<p>${esc(item.text)}</p>`:''}<div class="chat-actions">${(item.actions||[]).map(a=>actionButton({...a,asOf:m.asOf})).join('')}</div></div>`).join('')}<div class="chat-actions">${(m.answer.actions||[]).map(a=>actionButton({...a,asOf:m.asOf})).join('')}</div>${sourceLinks(m.answer)}${m.answer.suggestions?suggestions(m.answer.suggestions):''}`:'<p class="chat-answer" role="status">Looking up the data…</p>'}</article>`).join('');
  $('#chat-starters').hidden=true;
  log.scrollTop=log.lastElementChild?log.lastElementChild.offsetTop-log.offsetTop:0;
 }
 function suggestions(labels){return labels.map(label=>`<button type="button" class="chat-suggestion" data-chat-question="${esc(label)}">${esc(label)} ${icon('chevron')}</button>`).join('');}
 function cleanResponse(value,c){
  if(!value||typeof value.text!=='string')throw new Error('Invalid response');
  function cleanActions(list){return (Array.isArray(list)?list:[]).slice(0,8).filter(a=>a&&['rule','source','facts','rules','sources','changes','affected','property'].includes(a.type)&&typeof a.label==='string'&&(!a.ruleId||E.rules[a.ruleId])&&(!a.testId||D.change_tests.some(t=>t.test_id===a.testId))&&(!a.propertyId||properties.some(p=>p.id===a.propertyId))).map(a=>({type:a.type,label:a.label.slice(0,100),ruleId:a.ruleId,testId:a.testId,city:c.property.city,propertyId:a.propertyId||c.property.id}));}
  return {sources:(Array.isArray(value.sources)?value.sources:[]).filter(s=>Number.isInteger(s.id)&&typeof s.quote==='string'&&sourcesById[s.docId]),text:value.text.slice(0,16000),items:(Array.isArray(value.items)?value.items:[]).slice(0,8).map(i=>({title:String(i.title||'').slice(0,250),text:String(i.text||'').slice(0,4000),actions:cleanActions(i.actions)})),actions:cleanActions(value.actions),suggestions:(Array.isArray(value.suggestions)?value.suggestions:[]).filter(s=>typeof s==='string').slice(0,3)};
 }
 async function ask(question){
  question=question.trim().slice(0,1500);if(!question||busy)return;
  if(mentionRange&&!picker.hidden){addressSearch.focus();return;}
  hideAddressPicker();
  const c=context(),provider=window.ParcelChatProvider;
  const m={question,address:displayAddress(c.property.address),asOf:c.asOf};
  history.push(m);busy=true;send.disabled=true;input.value='';resize();open();render();
  let timeout;
  const controller=new AbortController();
  try{
   const request=provider.reply({message:question,context:c,history:history.slice(0,-1).map(h=>({question:h.question,answer:{text:(h.answer?.text||'').slice(0,8000)},address:h.address,asOf:h.asOf})),signal:controller.signal});
   const response=await Promise.race([request,new Promise((_,reject)=>{timeout=setTimeout(()=>{controller.abort();reject(new Error('Timed out'));},100000);})]);
   m.answer=cleanResponse(response,c);
  }catch(error){m.answer={text:error.message||'The answer could not load. Please try again.',suggestions:[question]};}
  finally{clearTimeout(timeout);busy=false;send.disabled=!input.value.trim();render();}
 }
 function resize(){input.style.height='auto';input.style.height=Math.min(input.scrollHeight,104)+'px';}
 function showRule(a){
  const p=properties.find(p=>p.id===a.propertyId),r=E.rules[a.ruleId];if(!p||!r)return;
  $('#as-of').value=a.asOf;chooseProperty(p.id);enabled.add(catOf[r.category]);renderLayers();renderDetail();
  const card=[...$('#detail').querySelectorAll('.engine-rule')].find(el=>el.dataset.rule===a.ruleId);
  if(card){card.querySelector('details').open=true;card.scrollIntoView({block:'nearest'});}
 }
 function runAction(a){
  if(!a)return;
  if(a.type==='source'){
   const r=E.rules[a.ruleId];if(!r)return;
   openModal('',`<header class="reading-header"><h2 id="reading-title">${esc(r.title)}</h2><div class="reading-publisher">${esc(r.citation||r.jurisdiction)}</div></header><div class="reading-scroll"><div class="reading-excerpt-label">Source excerpt</div><blockquote class="reading-excerpt">${esc(r.quoted_span)}</blockquote></div><footer class="reading-footer"><a href="${safeUrl(r.source_url)}" target="_blank" rel="noopener">Open original source ${icon('external')}</a></footer>`,'reading-dialog');
  }else if(a.type==='affected'){
   const t=D.change_tests.find(t=>t.test_id===a.testId);if(!t)return;
   const ids=new Set(changeIds(t.test_id,'affected_address_ids')),ps=properties.filter(p=>ids.has(p.id)&&p.city===a.city);
   openModal('AFFECTED PROPERTIES',`<h2>${esc(t.title)}</h2><p>${esc(t.as_of_before?`${t.as_of_before} → ${t.as_of_after}`:t.as_of)}${t.type==='pending'?' — if enacted':''}</p><div class="candidate-list">${ps.map(p=>`<button class="search-result" data-chat-property="${p.id}" data-chat-date="${t.as_of_after||t.as_of}"><strong>${esc(displayAddress(p.address))}</strong><small>${esc(cities[p.city].name)}</small></button>`).join('')}</div>`);
  }else if(a.type==='rule'){showRule(a);}
  else if(a.type==='changes'){setView('changes');}
  else{
   if(a.asOf)$('#as-of').value=a.asOf;
   chooseProperty(a.propertyId);
   if(a.type==='facts'){detailTab='facts';renderDetail();}
   if(a.type==='sources'){sourceFilter='property';setView('sources');}
  }
  sync();
 }
 function hideAddressPicker(){picker.hidden=true;mentionRange=null;$('#chat-address-tag').setAttribute('aria-expanded','false');input.removeAttribute('aria-activedescendant');addressSearch.removeAttribute('aria-activedescendant');}
 function highlightAddress(){
  picker.querySelectorAll('[data-chat-address]').forEach((button,i)=>{button.setAttribute('aria-selected',String(i===addressActive));if(i===addressActive)button.scrollIntoView({block:'nearest'});});
  const active=addressMatches[addressActive];
  for(const field of [input,addressSearch]){if(active)field.setAttribute('aria-activedescendant','chat-option-'+active.id);else field.removeAttribute('aria-activedescendant');}
 }
 function filterAddresses(query){
  const terms=query.toLowerCase().trim().split(/\s+/).filter(Boolean);
  addressMatches=properties.filter(p=>terms.every(term=>`${p.id} ${p.address} ${p.postal_city} ${cities[p.city].name}`.toLowerCase().includes(term))).sort((a,b)=>(b.id===selected.id)-(a.id===selected.id)||(b.city===selected.city)-(a.city===selected.city)).slice(0,8);
  addressActive=0;
  $('#chat-address-options').innerHTML=addressMatches.map(p=>`<button type="button" id="chat-option-${p.id}" role="option" aria-selected="false" tabindex="-1" data-chat-address="${p.id}"><strong>${esc(displayAddress(p.address))}</strong><small>${esc(cities[p.city].name)}, ${esc(p.state)}</small></button>`).join('');
  $('#chat-address-empty').hidden=addressMatches.length>0;highlightAddress();
 }
 function showAddressPicker(query='',focus=false){picker.hidden=false;$('#chat-address-tag').setAttribute('aria-expanded','true');addressSearch.value=query;filterAddresses(query);if(focus)addressSearch.focus();}
 function detectMention(){
  const before=input.value.slice(0,input.selectionStart),match=before.match(/(?:^|\s)@([^@\n]*)$/);
  if(!match){if(mentionRange)hideAddressPicker();return;}
  mentionRange={start:before.length-match[1].length-1,end:input.selectionStart};showAddressPicker(match[1]);
 }
 function selectAddress(id){
  if(!properties.some(p=>p.id===id))return;
  let caret=input.selectionStart;
  if(mentionRange){caret=mentionRange.start;input.value=input.value.slice(0,mentionRange.start)+input.value.slice(mentionRange.end);}
  hideAddressPicker();chooseProperty(id);sync();resize();send.disabled=busy||!input.value.trim();input.focus();input.setSelectionRange(caret,caret);
 }
 function addressKeys(e){
  if(picker.hidden||e.isComposing)return false;
  if(['ArrowDown','ArrowUp'].includes(e.key)){e.preventDefault();if(addressMatches.length){addressActive=(addressActive+(e.key==='ArrowDown'?1:-1)+addressMatches.length)%addressMatches.length;highlightAddress();}return true;}
  if(e.key==='Enter'){e.preventDefault();if(addressMatches[addressActive])selectAddress(addressMatches[addressActive].id);return true;}
  if(e.key==='Escape'){e.preventDefault();hideAddressPicker();input.focus();return true;}
  if(e.key==='Tab')hideAddressPicker();
  return false;
 }
 $('#chat-address-tag').addEventListener('click',()=>{if(picker.hidden){mentionRange=null;showAddressPicker('',true);}else hideAddressPicker();});
 addressSearch.addEventListener('input',()=>filterAddresses(addressSearch.value));
 addressSearch.addEventListener('keydown',addressKeys);
 $('#chat-address-options').addEventListener('click',e=>{const button=e.target.closest('[data-chat-address]');if(button)selectAddress(button.dataset.chatAddress);});
 document.addEventListener('click',e=>{if(!e.target.closest('#chat-address-picker,#chat-address-tag,#chat-input'))hideAddressPicker();});
 $('#chat-form').addEventListener('submit',e=>{e.preventDefault();ask(input.value);});
 input.addEventListener('input',()=>{resize();send.disabled=busy||!input.value.trim();detectMention();});
 input.addEventListener('keydown',e=>{if(addressKeys(e))return;if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();ask(input.value);}if(e.key==='Escape'){close();input.blur();}});
 $('#chat-close').addEventListener('click',close);
 $('#chat-resume').addEventListener('click',()=>{open();input.focus();});
 root.addEventListener('click',e=>{const b=e.target.closest('button');if(!b)return;if(b.dataset.chatQuestion)ask(b.dataset.chatQuestion);if(b.dataset.chatAction!==undefined)runAction(actions[Number(b.dataset.chatAction)]);if(b.dataset.chatCitation!==undefined)showCitation(citations[Number(b.dataset.chatCitation)]);});
 $('#modal-body').addEventListener('click',e=>{const b=e.target.closest('[data-chat-property]');if(b){$('#as-of').value=b.dataset.chatDate;$('#modal').close();chooseProperty(b.dataset.chatProperty);sync();}});
 new MutationObserver(sync).observe($('#detail'),{childList:true});
 document.addEventListener('click',sync);$('#as-of').addEventListener('change',sync);
 document.addEventListener('parcel-language-change',sync);
 $('#chat-starters').hidden=true;
 sync();
})();
