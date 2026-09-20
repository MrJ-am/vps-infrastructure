'use strict';
const $ = (s, root = document) => root.querySelector(s);
const $$ = (s, root = document) => [...root.querySelectorAll(s)];
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num = (n, digits=1) => n == null ? '—' : Number(n).toLocaleString('fr-FR',{maximumFractionDigits:digits});
const date = (v, short=false) => v ? new Date(v).toLocaleDateString('fr-FR',short ? {day:'numeric',month:'short'} : {day:'numeric',month:'long',year:'numeric',hour:'2-digit',minute:'2-digit'}) : '—';
const localDate = value => { if (!value) return ''; const d = new Date(value); return new Date(d.getTime()-d.getTimezoneOffset()*60000).toISOString().slice(0,16); };
const iso = value => value ? new Date(value).toISOString() : null;
const states = [['active','Toutes les fiches'],['due','À réviser'],['new','Nouvelles'],['scheduled','Planifiées'],['unscheduled','Sans échéance'],['archived','Archivées'],['all','Archives comprises']];
const stateName = key => ({new:'Nouvelle',due:'À réviser',scheduled:'Planifiée',unscheduled:'Sans échéance',archived:'Archivée'})[key] || key;
const outcomes = {recalled:'Rappel réussi',partial:'Rappel partiel',forgotten:'Oubli',not_assessed:'Non évalué'};
const ratings = {1:'À revoir',2:'Difficile',3:'Correct',4:'Facile'};
const state = {csrf:null,user:null,filter:{query:'',tags:[],tagMode:'all',state:'active',sort:'updatedAt',direction:'desc',limit:25,offset:0},list:[],tags:[],counts:{},total:0,selected:null,data:null,draft:null,dirty:false,editing:false,tab:'content',observationOffset:0,request:0,detailRequest:0,saving:false,correction:null};
function notice(message='',error=false){$('#notice').textContent=message;$('#notice').classList.toggle('error',error);}
function loginView(){ $('#loading').hidden=true;$('#login').hidden=false;$('#workspace').hidden=true;$('#account').hidden=true; }
function workspaceView(){ $('#loading').hidden=true;$('#login').hidden=true;$('#workspace').hidden=false;$('#account').hidden=false;$('#username').textContent=state.user; }
async function request(path,data,auth=true){
  const response=await fetch(path,{method:data===undefined?'GET':'POST',credentials:'same-origin',cache:'no-store',headers:{...(data===undefined?{}:{'Content-Type':'application/json'}),...(state.csrf?{'X-CSRF-Token':state.csrf}:{})},body:data===undefined?undefined:JSON.stringify(data)});
  let payload;try{payload=await response.json();}catch{throw new Error('Le serveur a renvoyé une réponse inattendue. Réessayez.');}
  if(response.status===401 && auth){state.csrf=null;state.request++;state.detailRequest++;loginView();throw new Error('Votre session a expiré. Reconnectez-vous ; les modifications en cours sont conservées.');}
  if(!response.ok){const messages={authentication_required:'Connectez-vous pour continuer.',invalid_credentials:'Identifiant ou mot de passe incorrect.',rate_limited:'Trop de tentatives. Patientez avant de réessayer.',csrf_required:'La session a changé. Rechargez la page après avoir conservé vos modifications.',conflict:'Cette fiche ou observation a été modifiée entre-temps. Vos changements sont conservés ici. Rechargez la fiche avant de les reporter.',not_found:'Cette fiche est introuvable.',invalid_data:'Vérifiez les valeurs, les dates et les limites des champs.',invalid_input:'Certains champs sont invalides.',unavailable:'Le service de connexion est temporairement indisponible.'};throw new Error(messages[payload.error] || payload.message || 'La demande a échoué. Réessayez.');}
  return payload;
}
const api=(action,payload)=>request('/api/web/'+action,payload);
function mayLeave(){if(state.saving){notice('Enregistrement en cours…');return false;}return !state.dirty || confirm('Des modifications ne sont pas enregistrées. Les abandonner ?');}
function dirty(){state.dirty=true;const el=$('#save-indicator');if(el)el.textContent='Modifications non enregistrées';}
function tagsHTML(tags){return tags.map(t=>`<span class="tag">${esc(t)}</span>`).join('');}
function renderSidebar(){
  $('#states').innerHTML=states.map(([key,name])=>`<button class="state-button ${state.filter.state===key?'active':''}" data-state="${key}" aria-pressed="${state.filter.state===key}"><span>${name}</span>${state.counts[key]===undefined?'':`<span class="count">${state.counts[key]}</span>`}</button>`).join('');
  $('#tag-count').textContent=state.tags.length;
  const term=$('#tag-search').value.toLocaleLowerCase('fr');
  $('#tags').innerHTML=state.tags.filter(t=>t.tag.toLocaleLowerCase('fr').includes(term)).map(t=>`<label class="tag-option"><input type="checkbox" data-tag="${esc(t.tag)}" ${state.filter.tags.includes(t.tag)?'checked':''}><span>${esc(t.tag)}</span><span class="count">${t.count}</span></label>`).join('') || '<p class="small muted">Aucun tag.</p>';
}
function renderList(){
  $('#result-count').textContent=`${num(state.total,0)} fiche${state.total>1?'s':''}`;
  $('#sheet-list').innerHTML=state.list.map(s=>`<tr class="${state.selected===s.id?'selected':''}"><td><button class="sheet-open" data-id="${s.id}" ${state.selected===s.id?'aria-current="true"':''}><strong>${esc(s.title)}</strong><span class="preview">${esc(s.summary)}</span><span class="mini-tags"><span class="badge ${s.state}">${stateName(s.state)}</span>${tagsHTML(s.tags.slice(0,2))}${s.tags.length>2?`<span class="tag">+${s.tags.length-2}</span>`:''}</span></button></td><td class="${s.dueAt && new Date(s.dueAt)<new Date()?'due-text':''}">${s.dueAt?esc(date(s.dueAt,true)):'—'}</td><td>${num(s.fsrsStability)}${s.fsrsStability==null?'':' j'}</td><td>${s.retrievability==null?'—':num(s.retrievability*100,0)+' %'}</td></tr>`).join('');
  $('#list-empty').hidden=state.list.length>0;$('#list-empty').textContent=state.total?'Aucune fiche sur cette page.':'Aucune fiche ne correspond à cette sélection.';
  $('#previous').disabled=state.filter.offset===0;$('#next').disabled=state.filter.offset+state.filter.limit>=state.total;
  $('#page-info').textContent=state.total?`${state.filter.offset+1}–${Math.min(state.filter.offset+state.filter.limit,state.total)} sur ${num(state.total,0)}`:'0 fiche';
  $('#direction').textContent=state.filter.direction==='asc'?'↑':'↓';$('#direction').setAttribute('aria-label',state.filter.direction==='asc'?'Ordre croissant':'Ordre décroissant');
}
async function loadList(reset=false){
  if(reset)state.filter.offset=0;const sequence=++state.request;$('#result-count').textContent='Recherche…';
  try{const result=await api('list',state.filter);if(sequence!==state.request)return;Object.assign(state,{list:result.sheets,tags:result.tags,counts:result.counts,total:result.total});renderSidebar();renderList();}
  catch(e){if(sequence===state.request){notice(e.message,true);$('#result-count').textContent='Recherche indisponible';}}
}
function draftFrom(s){return {title:s.title,body:s.body,summary:s.summary,tags:[...s.tags],aliases:[...s.aliases],importance:s.importance,dueAt:s.dueAt,fsrsStability:s.fsrsStability,fsrsDifficulty:s.fsrsDifficulty,fsrsLastReviewedAt:s.fsrsLastReviewedAt,archived:!!s.archivedAt};}
async function selectSheet(id,force=false){
  if(!force && !mayLeave())return;const sequence=++state.detailRequest;
  try{const data=await api('get',{sheetId:id,observationOffset:0});if(sequence!==state.detailRequest)return;Object.assign(state,{selected:id,data,draft:draftFrom(data.sheet),dirty:false,editing:false,tab:'content',observationOffset:0});notice();renderDetail();renderList();$('#workspace').classList.add('editing-focus');if(matchMedia('(max-width:700px)').matches)$('#detail').scrollIntoView({block:'start'});}
  catch(e){if(sequence===state.detailRequest)notice(e.message,true);}
}
function inline(text){
  return esc(text).replace(/`([^`]+)`/g,'<code>$1</code>').replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>').replace(/\*([^*]+)\*/g,'<em>$1</em>');
}
function markdown(text){
  // Raw HTML and external images are never interpreted as executable content.
  const blocks=text.split(/(```[\s\S]*?```)/g);
  return blocks.map(block=>block.startsWith('```')?`<pre><code>${esc(block.replace(/^```[^\n]*\n?/,'').replace(/```$/,''))}</code></pre>`:block.split(/\n\s*\n/).filter(Boolean).map(p=>{
    if(/^#{1,6} /.test(p)){const h=Math.min(3,p.match(/^#+/)[0].length+1);return `<h${h}>${inline(p.replace(/^#+ /,''))}</h${h}>`;}
    if(p.split('\n').every(l=>/^[-*] /.test(l)))return `<ul>${p.split('\n').map(l=>`<li>${inline(l.slice(2))}</li>`).join('')}</ul>`;
    if(p.startsWith('> '))return `<blockquote>${inline(p.replace(/^> /gm,'')).replace(/\n/g,'<br>')}</blockquote>`;
    return `<p>${inline(p).replace(/\n/g,'<br>')}</p>`;
  }).join('')).join('');
}
function field(name,label,type='text',extra=''){
  const d=state.draft;let value=d[name]??'';if(type==='datetime-local')value=localDate(value);if(Array.isArray(value))value=value.join(', ');
  return `<label>${label}<input name="${name}" type="${type}" value="${esc(value)}" ${extra}></label>`;
}
function contentPane(){
  const d=state.draft;
  if(!state.editing)return `<div class="prose">${markdown(d.body)}</div>${d.summary?`<div><p class="eyebrow">Synthèse</p><p class="small muted">${esc(d.summary)}</p></div>`:''}<div class="mini-tags">${tagsHTML(d.tags)}</div>${d.aliases.length?`<p class="small muted">Alias : ${esc(d.aliases.join(' · '))}</p>`:''}`;
  return `<form id="sheet-form">${field('title','Titre','text','required maxlength="200"')}<label>Contenu<textarea name="body" rows="14" required maxlength="50000">${esc(d.body)}</textarea></label><p class="small muted">Texte ou Markdown. Le HTML est affiché comme du texte.</p><label>Synthèse<textarea name="summary" rows="3" maxlength="2000">${esc(d.summary)}</textarea></label>${field('tags','Tags · séparés par des virgules')}${field('aliases','Alias · séparés par des virgules')}<p class="small muted">Jusqu’à 50 tags et 50 alias.</p></form>`;
}
function parametersPane(){
  const d=state.draft,s=state.data?.sheet;
  const metrics=`<div class="metric-grid"><div class="metric"><span class="label">Stabilité</span><span class="value">${num(d.fsrsStability)}${d.fsrsStability==null?'':' <small>j</small>'}</span></div><div class="metric"><span class="label">Difficulté</span><span class="value">${num(d.fsrsDifficulty)} <small>/ 10</small></span></div><div class="metric"><span class="label">Rappel estimé</span><span class="value">${s?.retrievability==null?'—':num(s.retrievability*100,0)+' <small>%</small>'}</span></div><div class="metric"><span class="label">Importance</span><span class="value">${d.importance} <small>/ 5</small></span></div></div>`;
  const params=state.editing?`<form id="sheet-form">${field('importance','Importance (1 à 5)','number','min="1" max="5" step="1" required')}${field('dueAt','Prochaine échéance','datetime-local')}<p class="small muted">Laissez l’échéance vide pour ne plus planifier la fiche.</p><div class="form-row">${field('fsrsStability','Stabilité (jours)','number','min="0.001" max="36500" step="any"')}${field('fsrsDifficulty','Difficulté (1 à 10)','number','min="1" max="10" step="any"')}</div>${field('fsrsLastReviewedAt','Date de référence du modèle','datetime-local')}<p class="small muted">Stabilité, difficulté et date de référence se renseignent ensemble. Une modification manuelle est historisée et ne crée pas de révision.</p><label class="check-label"><input name="archived" type="checkbox" ${d.archived?'checked':''}>Archiver cette fiche</label></form>`:`${metrics}<dl class="key-values"><dt>Prochaine échéance</dt><dd>${esc(date(d.dueAt))}</dd><dt>Dernière observation</dt><dd>${esc(date(s?.lastReviewedAt))}</dd><dt>Observations enregistrées</dt><dd>${num(s?.reviewCount,0)}</dd><dt>Révisions notées</dt><dd>${num(s?.fsrsReviewCount,0)}</dd><dt>Date de référence</dt><dd>${esc(date(d.fsrsLastReviewedAt))}</dd><dt>Dernier résultat</dt><dd>${esc(outcomes[s?.lastOutcome]||'—')}</dd><dt>Créée le</dt><dd>${esc(date(s?.createdAt))}</dd><dt>Modifiée le</dt><dd>${esc(date(s?.updatedAt))}</dd></dl>`;
  const settings=state.data?.settings;
  return `${params}${settings?`<details class="settings"><summary>Modèle de révision · ${esc(settings.modelVersion)}</summary><p class="small muted">Rétention cible : ${num(settings.desiredRetention*100,0)} %. Le rappel affiché est une estimation calculée à partir du modèle actuel.</p><p class="small muted">${esc(settings.implementationVersion)} · Paramètres globaux</p><pre>${esc(JSON.stringify(settings.parameters,null,2))}</pre></details>`:''}${state.data?.edits.length?`<details class="settings"><summary>Modifications manuelles récentes</summary>${state.data.edits.map(e=>`<p class="small muted">${esc(date(e.createdAt))} · ${esc(e.author)}</p>`).join('')}</details>`:''}`;
}
function observationsPane(){
  const data=state.data;if(!data?.observationTotal)return '<div class="empty"><h3>Aucune observation pour le moment</h3><p>Les informations enregistrées lors des échanges apparaîtront ici.</p></div>';
  return data.observations.map(o=>`<article class="observation"><div class="observation-heading"><strong>${esc(outcomes[o.outcome]||o.outcome)}</strong><time>${esc(date(o.reviewedAt))}</time></div><p>${esc(o.note)}</p>${o.rating?`<p class="small muted">Note ${o.rating} · ${ratings[o.rating]}${o.schedulingApplied?' · Révision planifiée':''}</p>`:''}<button class="quiet" data-correct="${o.id}">Corriger l’observation</button><details><summary>Informations enregistrées</summary><pre>${esc(JSON.stringify(o.context,null,2))}</pre></details>${o.schedulingApplied?`<details><summary>Paramètres de cette révision</summary><dl class="key-values"><dt>Stabilité avant / après</dt><dd>${num(o.previousStability)} / ${num(o.newStability)} j</dd><dt>Difficulté avant / après</dt><dd>${num(o.previousDifficulty)} / ${num(o.newDifficulty)}</dd><dt>Jours écoulés</dt><dd>${num(o.elapsedDays,0)}</dd><dt>Intervalle planifié</dt><dd>${num(o.scheduledDays,0)} j</dd><dt>Échéance</dt><dd>${esc(date(o.nextReviewAt))}</dd><dt>Rétention cible</dt><dd>${num(o.desiredRetention*100,0)} %</dd><dt>Modèle</dt><dd>${esc(o.schedulerVersion)}</dd></dl></details>`:''}${o.original?`<details><summary>Version originale · corrigée le ${esc(date(o.correctedAt))}</summary><p>${esc(o.original.note)}</p><pre>${esc(JSON.stringify(o.original.context,null,2))}</pre></details>`:''}</article>`).join('')+`<div class="pagination"><button class="quiet" id="obs-previous" ${state.observationOffset===0?'disabled':''}>← Précédentes</button><span>${state.observationOffset+1}–${Math.min(state.observationOffset+50,data.observationTotal)} / ${data.observationTotal}</span><button class="quiet" id="obs-next" ${state.observationOffset+50>=data.observationTotal?'disabled':''}>Suivantes →</button></div>`;
}
function renderDetail(){
  if(!state.draft)return;const s=state.data?.sheet;
  $('#detail').innerHTML=`<div class="detail-header"><div class="detail-meta"><button class="quiet mobile-back" id="back-list">← Fiches</button><span class="eyebrow">${s?'Fiche '+s.id:'Nouvelle fiche'}</span>${state.editing?'<span class="badge">Édition</span>':'<button class="secondary small" id="edit-sheet">Modifier</button>'}</div><h2>${esc(state.draft.title||'Une nouvelle idée')}</h2>${s?`<p class="small muted">${stateName(s.state)} · ${num(s.reviewCount,0)} observation${s.reviewCount>1?'s':''}</p>`:''}</div><div class="detail-tabs" role="tablist" aria-label="Informations de la fiche">${[['content','Contenu'],['observations','Observations'],['parameters','Paramètres']].map(([id,label])=>`<button role="tab" id="tab-${id}" data-tab="${id}" class="${state.tab===id?'active':''}" aria-selected="${state.tab===id}" aria-controls="pane-${id}">${label}</button>`).join('')}</div><div class="detail-content" role="tabpanel" id="pane-${state.tab}" aria-labelledby="tab-${state.tab}">${state.tab==='content'?contentPane():state.tab==='parameters'?parametersPane():observationsPane()}</div>${state.editing?`<div class="save-bar"><button class="quiet" id="cancel-edit">Annuler</button><button class="primary" id="save-sheet" ${state.saving?'disabled':''}>${state.saving?'Enregistrement…':'Enregistrer'}</button></div><p id="save-indicator" class="small muted">${state.dirty?'Modifications non enregistrées':''}</p>`:''}`;
  const form=$('#sheet-form');if(form&&state.saving)$$('input,textarea,select',form).forEach(el=>el.disabled=true);if(form)form.addEventListener('submit',e=>{e.preventDefault();saveSheet();});
}
function captureField(el){
  if(!el.name || !state.draft)return;const name=el.name;
  if(name==='tags'||name==='aliases')state.draft[name]=[...new Set(el.value.split(/[,\n]/).map(s=>s.trim()).filter(Boolean).map(s=>name==='tags'?s.toLowerCase():s))];
  else if(el.type==='checkbox')state.draft[name]=el.checked;
  else if(el.type==='number')state.draft[name]=el.value===''?null:Number(el.value);
  else if(el.type==='datetime-local')state.draft[name]=iso(el.value);
  else state.draft[name]=el.value;
  dirty();
}
async function saveSheet(){
  if(state.saving)return;const form=$('#sheet-form');if(form&&!form.reportValidity())return;
  const d=state.draft;
  if(!d.title.trim()||!d.body.trim()){notice('Le titre et le contenu sont obligatoires.',true);state.tab='content';renderDetail();return;}
  if(d.tags.length>50||d.aliases.length>50||d.tags.some(t=>t.length>64)||d.aliases.some(t=>t.length>120)){notice('Maximum : 50 tags de 64 caractères et 50 alias de 120 caractères.',true);return;}
  const tri=[d.fsrsStability,d.fsrsDifficulty,d.fsrsLastReviewedAt];if(tri.some(v=>v==null)&&!tri.every(v=>v==null)){notice('Renseignez ensemble la stabilité, la difficulté et la date de référence, ou laissez les trois vides.',true);return;}
  state.saving=true;renderDetail();
  try{const result=await api('save',{...d,...(state.selected?{sheetId:state.selected,expectedUpdatedAt:state.data.sheet.updatedAt}:{})});state.dirty=false;await selectSheet(result.sheetId,true);notice('Fiche enregistrée.');await loadList();}
  catch(e){notice(e.message,true);}finally{state.saving=false;renderDetail();}
}
async function changeObservationPage(delta){
  const selected=state.selected,offset=state.observationOffset+delta;
  try{const data=await api('get',{sheetId:selected,observationOffset:offset});if(selected!==state.selected)return;state.data.observations=data.observations;state.data.observationTotal=data.observationTotal;state.observationOffset=offset;renderDetail();}
  catch(e){notice(e.message,true);}
}
$('#login-form').addEventListener('submit',async e=>{e.preventDefault();const button=$('button[type=submit]',e.currentTarget);button.disabled=true;$('#login-error').textContent='';try{const form=new FormData(e.currentTarget);const result=await request('/auth/login',{username:form.get('username'),password:form.get('password')},false);e.target.elements.password.value='';state.csrf=result.csrf;state.user=result.username;workspaceView();await loadList();}catch(err){$('#login-error').textContent=err.message;}finally{button.disabled=false;}});
$('#logout').addEventListener('click',async()=>{if(!mayLeave())return;try{await request('/auth/logout',{});Object.assign(state,{csrf:null,user:null,list:[],tags:[],counts:{},data:null,draft:null,selected:null,dirty:false});state.request++;state.detailRequest++;$('#sheet-list').replaceChildren();$('#detail').replaceChildren();$('#tags').replaceChildren();loginView();}catch(e){notice(e.message,true);}});
$('#new-sheet').addEventListener('click',()=>{if(!mayLeave())return;state.detailRequest++;Object.assign(state,{selected:null,data:null,draft:{title:'',body:'',summary:'',tags:[],aliases:[],importance:3,dueAt:new Date().toISOString(),fsrsStability:null,fsrsDifficulty:null,fsrsLastReviewedAt:null,archived:false},dirty:false,editing:true,tab:'content'});notice();renderDetail();renderList();$('#workspace').classList.add('editing-focus');$('input[name=title]').focus();});
$('#search-form').addEventListener('submit',e=>{e.preventDefault();state.filter.query=$('#query').value.trim();loadList(true);});
$('#states').addEventListener('click',e=>{const button=e.target.closest('[data-state]');if(button){state.filter.state=button.dataset.state;loadList(true);}});
$('#tags').addEventListener('change',e=>{const tag=e.target.dataset.tag;if(tag){state.filter.tags=state.filter.tags.filter(t=>t!==tag);if(e.target.checked)state.filter.tags.push(tag);loadList(true);}});
$('#tag-search').addEventListener('input',renderSidebar);
$('#tag-mode').addEventListener('change',e=>{state.filter.tagMode=e.target.value;loadList(true);});
$('#sort').addEventListener('change',e=>{state.filter.sort=e.target.value;state.filter.direction=['title','dueAt','fsrsDifficulty','retrievability'].includes(e.target.value)?'asc':'desc';loadList(true);});
$('#direction').addEventListener('click',()=>{state.filter.direction=state.filter.direction==='asc'?'desc':'asc';loadList(true);});
$('#previous').addEventListener('click',()=>{state.filter.offset=Math.max(0,state.filter.offset-state.filter.limit);loadList();});
$('#next').addEventListener('click',()=>{state.filter.offset+=state.filter.limit;loadList();});
$('#apply-filters').addEventListener('click',()=>{let count=0;for(const el of $$('[id^="filter-"]')){if(!el.reportValidity())return;const key=el.id.slice(7);delete state.filter[key];if(el.value){count++;if(el.type==='date')state.filter[key]=new Date(el.value+(key==='dueBefore'?'T23:59:59.999':'T00:00:00')).toISOString();else state.filter[key]=Number(el.value)/(key==='maxRetrievability'?100:1);}}$('#active-filters').textContent=count?`· ${count}`:'';loadList(true);});
$('#reset-filters').addEventListener('click',()=>{state.filter={query:'',tags:[],tagMode:'all',state:'active',sort:'updatedAt',direction:'desc',limit:25,offset:0};$('#query').value='';$('#tag-search').value='';$('#tag-mode').value='all';$('#sort').value='updatedAt';$$('[id^="filter-"]').forEach(el=>el.value='');$('#active-filters').textContent='';loadList(true);});
$('#sheet-list').addEventListener('click',e=>{const button=e.target.closest('[data-id]');if(button)selectSheet(Number(button.dataset.id));});
$('#detail').addEventListener('input',e=>{if(e.target.closest('#sheet-form'))captureField(e.target);});
$('#detail').addEventListener('click',e=>{
  const button=e.target.closest('button');if(!button)return;
  if(button.dataset.tab){state.tab=button.dataset.tab;renderDetail();}
  if(button.id==='edit-sheet'){state.editing=true;renderDetail();}
  if(button.id==='save-sheet')saveSheet();
  if(button.id==='cancel-edit'&&mayLeave()){state.dirty=false;state.editing=false;if(state.data){state.draft=draftFrom(state.data.sheet);renderDetail();}else{state.draft=null;$('#detail').innerHTML='<div class="empty">Sélectionnez une fiche.</div>';$('#workspace').classList.remove('editing-focus');}}
  if(button.id==='back-list')$('#workspace').classList.remove('editing-focus');
  if(button.id==='obs-previous')changeObservationPage(-50);
  if(button.id==='obs-next')changeObservationPage(50);
  if(button.dataset.correct){state.correction=state.data.observations.find(o=>o.id===Number(button.dataset.correct));const form=$('#observation-form');form.elements.note.value=state.correction.note;form.elements.context.value=JSON.stringify(state.correction.context,null,2);$('#observation-error').textContent='';$('#observation-dialog').showModal();}
});
$('#cancel-observation').addEventListener('click',()=>$('#observation-dialog').close());
$('#observation-form').addEventListener('submit',async e=>{e.preventDefault();const form=e.currentTarget,button=$('button[type=submit]',form);button.disabled=true;try{let context;try{context=JSON.parse(form.elements.context.value);}catch{throw new Error('Les informations complémentaires doivent être un objet JSON valide.');}if(!context||Array.isArray(context)||typeof context!=='object')throw new Error('Le contexte doit être un objet JSON.');await api('correct',{observationId:state.correction.id,expectedCorrectionId:state.correction.correctionId,note:form.elements.note.value,context});$('#observation-dialog').close();await changeObservationPage(0);notice('Observation corrigée. La version originale est conservée.');}catch(err){$('#observation-error').textContent=err.message;}finally{button.disabled=false;}});
window.addEventListener('beforeunload',e=>{if(state.dirty){e.preventDefault();e.returnValue='';}});
(async()=>{try{const result=await request('/auth/session',undefined,false);state.csrf=result.csrf;state.user=result.username;workspaceView();await loadList();}catch(e){loginView();if(!e.message.includes('Connectez-vous'))$('#login-error').textContent=e.message;}})();
