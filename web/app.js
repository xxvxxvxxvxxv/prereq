/* All catalog strings are rendered as text nodes. No remote HTML is inserted. */
(function () {
  'use strict';
  const M=window.PrereqModel, $=id=>document.getElementById(id), SVG='http://www.w3.org/2000/svg';
  const preview=Boolean(window.__PREVIEW_SEED__);
  const state={seed:null,degree:null,courses:{},details:{},marks:{},query:'',filter:'all',view:'graph',expanded:new Set(),focus:null,selected:null,meta:null,layout:null,transform:{x:0,y:0,k:1},degreeToken:0,detailToken:0,listLimit:100,focusMode:'unlocks',indexMeta:null,catalogTerm:null,scheduleTerm:'202601',offerings:{},offeringMeta:{}};
  let mainAbort=null, detailAbort=null, indexAbort=null, scheduleAbort=null, toastTimer=null, resizeTimer=null, lastFocus=null, lastDrag=false;
  const el=(tag,className,text)=>{const n=document.createElement(tag);if(className)n.className=className;if(text!==undefined)n.textContent=text;return n;};
  const button=(text,className,fn)=>{const n=el('button',className,text);n.type='button';n.addEventListener('click',fn);return n;};
  const svgEl=(tag,attrs={},text)=>{const n=document.createElementNS(SVG,tag);for(const[k,v]of Object.entries(attrs))n.setAttribute(k,String(v));if(text!==undefined)n.textContent=text;return n;};
  const shorten=(s,n=36)=>s?.length>n?s.slice(0,n-1)+'…':s||'';
  const getLocal=k=>{try{return localStorage.getItem(k);}catch{return null;}};
  const setLocal=(k,v)=>{try{localStorage.setItem(k,v);return true;}catch{return false;}};
  const planKey=()=>`prereq.plan.v1:${state.degree.program.id}:${state.degree.term}`;
  const dateLabel=value=>{if(!value)return 'Unknown';const d=new Date(value);return Number.isNaN(d.getTime())?'Unknown':d.toLocaleDateString('en-GB',{day:'numeric',month:'short',year:'numeric'});};
  function toast(message,error=false){clearTimeout(toastTimer);$('toast').textContent=message;$('toast').classList.toggle('error',error);$('toast').hidden=false;toastTimer=setTimeout(()=>$('toast').hidden=true,6500);}
  function externalLink(label,url){const a=el('a','source-link',label);try{const u=new URL(url);if(u.protocol==='https:'&&['suis.sabanciuniv.edu','www.sabanciuniv.edu','sabanciuniv.edu','apps.sabanciuniv.edu'].includes(u.hostname)){a.href=u.href;a.target='_blank';a.rel='noopener noreferrer';}else a.removeAttribute('href');}catch{}return a;}
  function heading(text){return el('h2','',text);}
  function text(textValue,className=''){return el('p',className,textValue);}
  function openInfo(title){$('info-content').replaceChildren();$('info-eyebrow').textContent=title;if(!$('info-dialog').open)$('info-dialog').showModal();return $('info-content');}
  function snapshotMeta(data){return {state:data?.complete===false?'partial':'snapshot',observedAt:data?.observedAt,refreshing:false,error:null,offline:preview};}
  // A fresh map never restores or pre-opens branches. Course markers stay saved.
  function defaultExpanded(){return new Set();}
  function updateMeta(meta){state.meta=meta;const name=meta.state==='verified'?'Degree checked':meta.state==='partial'?'Partial degree':meta.state==='stale'?'Stale cache':meta.state==='snapshot'?'Snapshot':'No data';$('source-label').textContent=meta.refreshing?'Checking…':name;$('source-dot').className=meta.refreshing?'loading':meta.state==='verified'?'live':'';$('refresh-button').classList.toggle('spin',Boolean(meta.refreshing));$('refresh-button').disabled=Boolean(meta.refreshing);const date=dateLabel(meta.observedAt);$('source-button').title=`${name} · ${date}${meta.error?' · '+meta.error:''}`;$('footer-status').textContent=meta.refreshing?'Checking degree requirements · saved map remains visible':meta.error?'Live check unavailable · '+(state.degree?'snapshot kept':'open Sources for details'):preview?`Offline preview · observed ${date}`:`${name} · ${date} · public catalog`;$('footer-status').title=meta.error||`Last successful observation: ${date}. Degree rules, catalog prerequisites and semester sections have separate sources.`;}
  async function api(path,method='GET',signal){const response=await fetch(path,{method,headers:{'X-Prereq-Client':'1'},signal,credentials:'same-origin',cache:'no-store'});const payload=await response.json();if(!response.ok)throw new Error(payload.error||'The catalog request failed.');return payload;}
  async function delay(ms,signal){return new Promise((resolve,reject)=>{if(signal?.aborted)return reject(new DOMException('Aborted','AbortError'));const done=()=>{signal?.removeEventListener('abort',cancel);resolve();};const timer=setTimeout(done,ms);function cancel(){clearTimeout(timer);reject(new DOMException('Aborted','AbortError'));}signal?.addEventListener('abort',cancel,{once:true});});}
  async function watch(path,callback,signal){for(let i=0;i<180;i++){const result=await api(path,'GET',signal);callback(result);if(!result.meta?.refreshing)return;await delay(i<5?1500:2500,signal);}toast('The source check is taking longer than expected. You can keep exploring the cached map.',true);}
  function validDegree(data,program,term){return data?.schemaVersion===1&&data.program?.id===program&&data.term===term&&['university','required','core','area','free'].every(id=>data.sections?.some(s=>s.id===id&&Array.isArray(s.courses)));}
  function restoreMarks(){state.marks={};try{const stored=JSON.parse(getLocal(planKey())||'null');if(stored)state.marks=M.validatePlan(stored,state.degree,{keepUnlisted:true});}catch{toast('A saved plan could not be read. Export a fresh plan after marking courses.',true);}}
  function applyDegree(data,reset=false){state.degree=data;state.courses=M.uniqueCourses(data);if(reset){restoreMarks();state.view='graph';state.expanded=defaultExpanded();state.query='';$('search').value='';$('search-results').hidden=true;state.filter='all';$('status-filter').value='all';state.focus=null;state.focusMode='unlocks';state.indexMeta=null;state.listLimit=100;closeCourse();}else{/* A partial/stale source refresh must not erase local course markers. */}const p=data.program;$('selected-major').textContent=p.name;$('selected-term').textContent=data.termLabel;$('empty-state').hidden=true;updatePlanCount();render(reset);if(!preview)startIndex();}
  async function loadDegree(program,term){mainAbort?.abort();detailAbort?.abort();indexAbort?.abort();mainAbort=new AbortController();const signal=mainAbort.signal;const token=++state.degreeToken;let applied=false,stamp='';state.details=scopedSeed();state.offerings={};state.offeringMeta={};const data=state.seed.degrees[program+':'+term];const p=state.seed.programs.find(p=>p.id===program);$('selected-major').textContent=p?.name||program;$('selected-term').textContent=term.slice(0,4)+' · admission';state.focus=null;state.selected=null;closeCourse();if(data){applyDegree(data,true);updateMeta(snapshotMeta(data));applied=true;stamp=data.origin+data.observedAt;}else{state.degree=null;state.courses={};state.marks={};$('viewport').replaceChildren();$('course-list').replaceChildren();showEmpty('Checking the official catalog','Loading this major’s own degree requirements and elective pools. The source can take several seconds.',true);updateMeta({state:'unavailable',refreshing:!preview});}$('chooser').close();setLocal('prereq.selection.v1',JSON.stringify({program,term}));if(preview){if(!data){showEmpty('No offline snapshot for this selection','No saved degree exists for this selection. The running Python app checks the official requirements for each major and admission term.',false);updateMeta({state:'unavailable',refreshing:false,offline:true});}return;}try{await watch(`api/degree?program=${encodeURIComponent(program)}&term=${encodeURIComponent(term)}`,result=>{if(token!==state.degreeToken)return;if(result.data){if(!validDegree(result.data,program,term))throw new Error('The returned catalog does not match this selection.');const next=result.data.origin+result.data.observedAt;if(next!==stamp){applyDegree(result.data,!applied);stamp=next;applied=true;}}updateMeta(result.meta);if(!applied&&!result.meta.refreshing)showEmpty('The live catalog is unavailable',result.meta.error||'No matching saved degree exists. The source error is shown here; another major is never substituted.',false);},signal);}catch(error){if(error.name==='AbortError')return;updateMeta({...state.meta,refreshing:false,error:error.message});if(!applied)showEmpty('The catalog could not be loaded',error.message,false);}}
  function showEmpty(title,message,loading){$('empty-state').hidden=false;$('empty-title').textContent=title;$('empty-message').textContent=message;$('empty-state').classList.toggle('loading',loading);}
  function updatePlanCount(){$('plan-count').textContent=Object.keys(state.marks).length;}
  function saveMarks(){const data={schemaVersion:1,program:state.degree.program.id,term:state.degree.term,marks:state.marks};if(!setLocal(planKey(),JSON.stringify(data)))toast('Browser storage is unavailable. Export your plan before closing this page.',true);updatePlanCount();}
  function mark(cid,status){if(!state.courses[cid])return;if(state.marks[cid]===status)delete state.marks[cid];else state.marks[cid]=status;saveMarks();render(false);if(state.selected===cid)renderCourse(cid);}
  const graphNodes=new Map(),graphEdges=new Map();
  let graphFrame=0,cameraFrame=0,renderOrigin=null;
  const motion=()=>!matchMedia('(prefers-reduced-motion: reduce)').matches;
  const ease=t=>1-Math.pow(1-t,3);
  function render(reset=false){
    if(!state.degree)return;
    $('back-to-degree').hidden=!state.focus;
    $('direction-label').textContent=state.focusMode==='requires'&&state.focus?'Course → prerequisites':'Prerequisite → course';
    $('graph-region').hidden=state.view!=='graph';$('list-region').hidden=state.view!=='list';
    $('graph-controls').hidden=state.view!=='graph';$('map-nav').hidden=state.view!=='graph';
    document.querySelector('.map-legend').hidden=state.view!=='graph';
    for(const v of ['graph','list']){$(v+'-tab').classList.toggle('active',state.view===v);$(v+'-tab').setAttribute('aria-pressed',String(state.view===v));}
    if(state.view==='list'){renderList();return;}
    if(state.focus&&state.focusMode==='requires')state.layout=M.layout(M.dependencyTree(state.focus,state.details,state.courses),new Set());
    else state.layout=M.forwardForest(state.degree,state.details,state.expanded,state.marks,{focus:state.focus,query:state.query,status:state.filter});
    const cv=M.coverage(state.details,state.courses);
    $('match-count').textContent=`${cv.checked}/${cv.total} prerequisites checked${state.indexMeta?.error?' · source unavailable':state.indexMeta?.refreshing?' · checking…':''}${state.layout.capped?' · view limit':''}`;
    $('match-count').title=state.indexMeta?.error||'Only checked prerequisite relationships become edges. Missing data does not mean no prerequisites.';
    renderGraph();
    // Opening or closing a branch NEVER calls fit, zoom, or recenter.
    if(reset)home(false);
  }
  function paintNode(item,n){
    const g=item.el;
    g.setAttribute('class',`graph-node kind-${n.kind} ${state.marks[n.label]||''} ${n.matched===false||n.statusMatch===false?'dimmed':''}`);
    g.setAttribute('aria-label',`${n.label}${n.subtitle?', '+n.subtitle:''}${n.expandable?', '+(n.open?'hide':'show')+' outgoing branches':''}`);
    g.setAttribute('data-code',n.course?.code||'');g.removeAttribute('aria-hidden');
    if(n.expandable)g.setAttribute('aria-expanded',String(n.open));else g.removeAttribute('aria-expanded');
    g.replaceChildren(svgEl('title',{},n.kind==='course'?`${n.label} · ${n.subtitle||''}\n${M.expressionLabel(state.details[n.label]?.prerequisite)}\n${n.count||0} outgoing links currently indexed. ${n.cycle?'Cycle stopped.':''}`:n.label));
    if(n.kind==='section'){
      g.append(svgEl('rect',{x:-12,y:-21,width:278,height:39,rx:5,class:'hit'}));
      g.append(svgEl('text',{x:0,y:2,class:'section-label'},n.label));
      g.append(svgEl('text',{x:212,y:2,class:'count'},String(n.count||0)));
      if(n.expandable)g.append(svgEl('text',{x:245,y:3,class:'expand-symbol'},n.open?'−':'+'));
      g.append(svgEl('path',{d:'M0 20H261',class:'section-rule'}));return;
    }
    g.append(svgEl('rect',{x:-12,y:-18,width:274,height:39,rx:5,class:'hit'}));
    if(n.kind==='course')g.append(svgEl('circle',{cx:0,cy:0,r:3.4,class:`dot subject-${M.subjectClass(n.label)}`}));
    else g.append(svgEl('circle',{cx:0,cy:0,r:2.4,class:'dot'}));
    g.append(svgEl('text',{x:13,y:n.subtitle?-2:4,class:'node-label'},shorten(n.label,31)));
    if(n.subtitle)g.append(svgEl('text',{x:13,y:15,class:'node-subtitle'},shorten(n.subtitle,34)));
    if(state.marks[n.label])g.append(svgEl('text',{x:104,y:-2,class:'mark-glyph'},state.marks[n.label]==='completed'?'✓':'◇'));
    if(n.badge)g.append(svgEl('text',{x:155,y:-2,class:'rule-badge'},n.badge));
    if(n.expandable){
      const toggle=svgEl('g',{'data-action':'toggle',class:'node-toggle'});
      toggle.append(svgEl('rect',{x:197,y:-17,width:39,height:37,rx:4,class:'toggle-hit'}));
      if(n.kind==='course')toggle.append(svgEl('text',{x:201,y:2,class:'count'},String(n.count)));
      toggle.append(svgEl('text',{x:225,y:3,class:'expand-symbol'},n.open?'−':'+'));g.append(toggle);
    }
    if(n.kind==='course'){
      const info=svgEl('g',{'data-action':'info',tabindex:0,role:'button','aria-label':`Details for ${n.label}`,class:'node-info'});
      info.append(svgEl('rect',{x:239,y:-17,width:23,height:37,rx:4,class:'toggle-hit'}));
      info.append(svgEl('text',{x:246,y:3,class:'info-symbol'},'i'));
      info.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.stopPropagation();e.preventDefault();openCourse(n.label);}});g.append(info);
    }
  }
  function renderGraph(){
    cancelAnimationFrame(graphFrame);
    const vp=$('viewport');let edgeLayer=vp.querySelector('.edge-layer'),nodeLayer=vp.querySelector('.node-layer');
    if(!edgeLayer){graphNodes.clear();graphEdges.clear();edgeLayer=svgEl('g',{class:'edge-layer','aria-hidden':'true'});nodeLayer=svgEl('g',{class:'node-layer'});vp.replaceChildren(edgeLayer,nodeLayer);}
    const desired=new Map(state.layout.nodes.map(n=>[n.id,n])),desiredEdges=new Map(state.layout.edges.map(e=>[e.id,e]));
    const parents=new Map(state.layout.edges.map(e=>[e.to.id,e.from.id]));
    const origin=renderOrigin&&graphNodes.get(renderOrigin)?.pos;renderOrigin=null;
    for(const n of state.layout.nodes){
      let item=graphNodes.get(n.id);
      if(!item){
        const parent=graphNodes.get(parents.get(n.id));const start=parent?{x:parent.pos.x+220,y:parent.pos.y}:origin?{x:n.x,y:origin.y}:{x:n.x-14,y:n.y};
        const g=svgEl('g',{'data-node':n.id,tabindex:0,role:'button',opacity:0,transform:`translate(${start.x} ${start.y})`});
        item={el:g,pos:{...start},opacity:0};graphNodes.set(n.id,item);nodeLayer.append(g);
        g.addEventListener('click',e=>{if(lastDrag)return;const action=e.target.closest('[data-action]')?.getAttribute('data-action');if(action==='info'){openCourse(item.view.label);return;}nodeAction(item.view);});
        g.addEventListener('keydown',e=>{if(e.target!==g)return;if(e.key==='Enter'||e.key===' '){e.preventDefault();nodeAction(item.view);}if(e.key==='i'&&item.view.kind==='course'){e.preventDefault();openCourse(item.view.label);}});
      }
      item.view=n;item.start={...item.pos};item.fromOpacity=item.opacity;item.target={x:n.x,y:n.y};item.toOpacity=1;item.exit=false;
      paintNode(item,n);
    }
    for(const [id,item] of graphNodes)if(!desired.has(id)){
      item.start={...item.pos};item.fromOpacity=item.opacity;item.toOpacity=0;item.exit=true;
      let ancestor=id;let parent=null;
      while(ancestor.includes('>')){ancestor=ancestor.slice(0,ancestor.lastIndexOf('>'));if(desired.has(ancestor)){parent=desired.get(ancestor);break;}}
      item.target=parent?{x:parent.x+220,y:parent.y}:origin?{x:item.pos.x,y:origin.y}:{x:item.pos.x-10,y:item.pos.y};
      item.el.setAttribute('aria-hidden','true');item.el.setAttribute('tabindex','-1');item.el.querySelectorAll('[tabindex]').forEach(e=>e.setAttribute('tabindex','-1'));
    }
    for(const e of state.layout.edges){let item=graphEdges.get(e.id);if(!item){const path=svgEl('path',{class:'edge','marker-end':'url(#arrow)'});item={el:path};graphEdges.set(e.id,item);edgeLayer.append(path);}item.edge=e;item.exit=false;}
    for(const [id,item] of graphEdges)if(!desiredEdges.has(id))item.exit=true;
    const started=performance.now(),duration=motion()?320:0;
    vp.setAttribute('data-animating',duration?'true':'false');
    function frame(time){
      const t=duration?Math.min(1,(time-started)/duration):1,k=ease(t);
      for(const item of graphNodes.values()){
        item.pos={x:item.start.x+(item.target.x-item.start.x)*k,y:item.start.y+(item.target.y-item.start.y)*k};
        item.opacity=item.fromOpacity+(item.toOpacity-item.fromOpacity)*k;
        item.el.setAttribute('transform',`translate(${item.pos.x} ${item.pos.y})`);item.el.setAttribute('opacity',String(item.opacity));
        if(!item.exit){item.el.removeAttribute('aria-hidden');item.el.setAttribute('tabindex','0');}
      }
      for(const item of graphEdges.values()){
        const a=graphNodes.get(item.edge.from.id),b=graphNodes.get(item.edge.to.id);if(!a||!b)continue;
        const x1=a.pos.x+265,x2=b.pos.x-12,mid=(x1+x2)/2;
        item.el.setAttribute('d',`M${x1},${a.pos.y}C${mid},${a.pos.y} ${mid},${b.pos.y} ${x2},${b.pos.y}`);
        item.el.setAttribute('opacity',String(Math.min(a.opacity,b.opacity)*(item.exit?1-k:1)));
      }
      if(t<1)graphFrame=requestAnimationFrame(frame);
      else {for(const[id,item]of graphEdges)if(item.exit){item.el.remove();graphEdges.delete(id);}for(const[id,item]of graphNodes)if(item.exit){item.el.remove();graphNodes.delete(id);}vp.setAttribute('data-animating','false');}
    }
    if(duration)graphFrame=requestAnimationFrame(frame);else frame(started);
    transform();
  }
  function nodeAction(n){
    if(n.expandable){renderOrigin=n.id;if(state.expanded.has(n.id))state.expanded.delete(n.id);else state.expanded.add(n.id);render(false);}
    else if(n.kind==='course')openCourse(n.course.code);
    else if(n.kind==='load')openCourse(n.code);
    else if(n.kind==='notice')toast(n.subtitle||'Open the official course source.');
  }
  function availableRect(){const b=$('graph').getBoundingClientRect();return {w:b.width,h:b.height,top:b.width<600?184:b.width<760?150:118,left:b.width<600?24:45,bottom:82};}
  function cameraTo(target,animated=true){
    cancelAnimationFrame(cameraFrame);const start={...state.transform},at=performance.now(),duration=animated&&motion()?300:0;
    function step(now){const p=duration?Math.min(1,(now-at)/duration):1,k=ease(p);state.transform={x:start.x+(target.x-start.x)*k,y:start.y+(target.y-start.y)*k,k:start.k+(target.k-start.k)*k};transform();if(p<1)cameraFrame=requestAnimationFrame(step);}
    if(duration)cameraFrame=requestAnimationFrame(step);else step(at);
  }
  function home(animated=true){const r=availableRect();cameraTo({x:r.left,y:r.top+10,k:r.w<600?.87:1},animated);}
  function fit(){if(!state.layout)return;const r=availableRect(),aw=Math.max(180,r.w-r.left-36),ah=Math.max(120,r.h-r.top-r.bottom);const k=Math.min(1,Math.max(.15,Math.min(aw/state.layout.width,ah/state.layout.height)));cameraTo({k,x:r.left+(aw-state.layout.width*k)/2,y:r.top+10},true);}
  function transform(){const t=state.transform;$('viewport').setAttribute('transform',`translate(${t.x} ${t.y}) scale(${t.k})`);$('zoom-level').textContent=Math.round(t.k*100)+'%';}
  function zoom(factor,x,y){cancelAnimationFrame(cameraFrame);const b=$('graph').getBoundingClientRect();x??=b.width/2;y??=b.height/2;const t=state.transform,k=Math.min(2.6,Math.max(.12,t.k*factor)),ratio=k/t.k;t.x=x-(x-t.x)*ratio;t.y=y-(y-t.y)*ratio;t.k=k;transform();}
  function jumpSection(section){
    state.focus=null;state.focusMode='unlocks';state.view='graph';render(false);
    const n=state.layout.nodes.find(n=>n.id==='section:'+section);if(!n)return;
    const r=availableRect();cameraTo({x:r.left,y:r.top+12-n.y*state.transform.k,k:state.transform.k},true);
  }
  function showUnlocks(cid){state.focus=cid;state.focusMode='unlocks';state.query='';$('search').value='';$('search-results').hidden=true;state.view='graph';state.expanded.add(`focus:${cid}`);closeCourse();render(true);}
  async function startIndex(){
    if(preview||!state.degree)return;
    indexAbort?.abort();indexAbort=new AbortController();
    const signal=indexAbort.signal,p=state.degree.program.id,t=state.degree.term,ct=state.catalogTerm;let previous='';
    try{for(let attempt=0;attempt<720;attempt++){
      const result=await api(`api/index?program=${encodeURIComponent(p)}&term=${encodeURIComponent(t)}${ct?'&catalogTerm='+encodeURIComponent(ct):''}`,'GET',signal);
      if(state.degree?.program.id!==p||state.degree?.term!==t||state.catalogTerm!==ct)return;
      state.indexMeta=result.meta;
      if(result.data?.details){
        if((result.data.catalogTerm||null)!==ct)throw new Error('Catalog-term mismatch. The old map was not overwritten.');
        const stamp=JSON.stringify(result.data.details),before=JSON.stringify(state.details[state.selected]);
        if(stamp!==previous){Object.assign(state.details,result.data.details);previous=stamp;render(false);
          if(state.selected&&before!==JSON.stringify(state.details[state.selected]))renderCourse(state.selected);}else render(false);
      }
      if(!result.meta?.refreshing)return;await delay(5000,signal);
    }}catch(e){if(e.name!=='AbortError'){state.indexMeta={error:e.message,refreshing:false};render(false);}}
  }
  function scopedSeed(){return {...(state.catalogTerm?state.seed.catalogDetails?.[state.catalogTerm]||{}:state.seed.details||{})};}
  function changeCatalog(){
    const value=$('catalog-term').value;
    state.catalogTerm=value==='snapshot'?null:value;
    setLocal('prereq.catalog-term.v1',value);
    indexAbort?.abort();detailAbort?.abort();scheduleAbort?.abort();state.detailToken++;
    state.details=scopedSeed();state.indexMeta=null;state.offerings={};state.offeringMeta={};
    closeCourse();render(false);startIndex();
  }
  async function loadCatalogTerms(){
    if(preview)return;
    try{await watch('api/catalog-terms',r=>{
      if(!r.data?.terms)return;
      for(const term of r.data.terms){
        if(![...$('catalog-term').options].some(o=>o.value===term.id)){
          const o=el('option','',term.label);o.value=term.id;$('catalog-term').append(o);
        }
      }
    });}catch(e){$('catalog-term').title='Could not refresh the term selector: '+e.message;}
  }
  function appendSchedule(box,cid){
    const part=el('section','course-section');part.append(el('h3','','Semester sections'));
    const selector=el('select','schedule-select');selector.setAttribute('aria-label','Offering semester');
    const options=[...$('catalog-term').options].filter(o=>o.value!=='snapshot');
    for(const o of options){const n=el('option','',o.textContent);n.value=o.value;selector.append(n);}
    if(!options.some(o=>o.value===state.scheduleTerm)){const o=el('option','',state.scheduleTerm);o.value=state.scheduleTerm;selector.append(o);}
    selector.value=state.scheduleTerm;selector.onchange=()=>{state.scheduleTerm=selector.value;scheduleAbort?.abort();renderCourse(cid);};
    part.append(selector);
    const key=state.scheduleTerm+':'+cid,value=state.offerings[key],meta=state.offeringMeta[key];
    if(value){
      part.append(text(value.offered?'Offered in the checked schedule':'No sections returned for this semester','muted-small'));
      for(const section of value.sections||[]){const row=el('div','schedule-row');row.append(externalLink(section.label||('CRN '+section.crn),section.source));
        for(const meeting of section.meetings||[])row.append(text(Object.entries(meeting).map(([k,v])=>k+': '+v).join(' · '),'muted-small'));
        part.append(row);}
      part.append(text('Schedule checked '+dateLabel(value.observedAt),'muted-small'));
    }else part.append(text(meta?.refreshing?'Checking the Dynamic Schedule…':'Offering status not checked. Catalog inclusion does not prove a class is offered.','muted-small'));
    if(meta?.error)part.append(text(meta.error,'notice-box'));
    if(!preview&&!meta?.refreshing)part.append(button(value?'Recheck sections':'Check sections','secondary',()=>loadSchedule(cid)));
    box.append(part);
  }
  async function loadSchedule(cid){
    if(preview)return;
    scheduleAbort?.abort();scheduleAbort=new AbortController();const signal=scheduleAbort.signal,t=state.scheduleTerm,key=t+':'+cid;
    state.offeringMeta[key]={refreshing:true};renderCourse(cid);
    try{await watch(`api/schedule?term=${encodeURIComponent(t)}&code=${encodeURIComponent(cid)}`,r=>{
      if(state.scheduleTerm!==t||state.selected!==cid)return;
      if(r.data){if(r.data.scheduleTerm!==t||r.data.code!==cid)throw new Error('Wrong course or semester returned by schedule.');state.offerings[key]=r.data;}
      state.offeringMeta[key]=r.meta;renderCourse(cid);
    },signal);}catch(e){state.offeringMeta[key]={refreshing:false,error:e.name==='AbortError'?null:e.message};if(e.name!=='AbortError'&&state.selected===cid)renderCourse(cid);}
  }
  function renderList(){const rows=[];const seen=new Set();const normal=M.normal(state.query);for(const s of state.degree.sections){for(const c of s.courses){if(seen.has(c.code))continue;seen.add(c.code);const markValue=state.marks[c.code]||'unmarked';if(normal&&!M.normal(c.code+' '+c.title).includes(normal)||state.filter!=='all'&&state.filter!==markValue)continue;rows.push({c,s,markValue});}}rows.sort((a,b)=>a.c.code.localeCompare(b.c.code,'en',{numeric:true}));$('match-count').textContent=rows.length+' course options';$('course-list').replaceChildren();for(const {c,s,markValue} of rows.slice(0,state.listLimit)){const branch=['area','free'].includes(s.id)?s.id:'core';const row=button('','course-row',()=>openCourse(c.code));const name=el('span','row-name');name.append(el('strong','',c.code),el('small','',c.title));const dot=el('i','subject-dot subject-'+M.subjectClass(c.code));name.prepend(dot);row.append(name,el('span','row-category '+branch,s.id==='required'?'Required':s.id==='university'?'University':s.category==='additional'?s.label:s.id[0].toUpperCase()+s.id.slice(1)),el('span','row-credits',`${c.credits} / ${c.ects}`),el('span','row-status '+markValue,markValue==='unmarked'?'○':markValue[0].toUpperCase()+markValue.slice(1)));$('course-list').append(row);}$('list-empty').hidden=rows.length>0;$('list-more').hidden=rows.length<=state.listLimit;}
  function searchResults(){const value=$('search').value.trim();state.query=value;state.listLimit=100;render(false);const box=$('search-results');box.replaceChildren();if(!value||!state.degree){box.hidden=true;return;}const found=Object.values(state.courses).filter(c=>M.normal(c.code+' '+c.title).includes(M.normal(value)));found.sort((a,b)=>Number(M.normal(b.code)===M.normal(value))-Number(M.normal(a.code)===M.normal(value))||a.code.localeCompare(b.code));for(const c of found.slice(0,7)){const row=button('','search-result',()=>{box.hidden=true;showUnlocks(c.code);});row.append(el('strong','',c.code),el('span','',c.title));box.append(row);}box.append(button(found.length?`View all ${found.length} matches →`:'No courses found','search-all',()=>{box.hidden=true;state.view='list';render();}));box.hidden=false;}
  function drawExpression(ast,container,noneLabel='No prerequisite listed.'){if(!ast||ast.type==='unknown'){container.append(text(ast?.reason||'Not loaded. Open the official source to verify.','muted-small'));return;}if(ast.type==='none'){container.append(text(noneLabel,'muted-small'));return;}if(ast.type==='course'){const c=button('','course-chip',()=>openCourse(ast.code));c.append(el('span','',ast.code));if(ast.minGrade)c.append(el('small','',`min ${ast.minGrade}`));if(ast.concurrentAllowed===true)c.append(el('small','','Concurrent enrollment allowed by this prerequisite clause'));container.append(c);return;}const group=el('div','logic-group');group.append(el('span','logic-label',ast.type==='and'?'ALL OF':'ANY OF'));for(const child of ast.children||[])drawExpression(child,group,noneLabel);container.append(group);}
  function renderCourse(cid,loading=false,error=null){if(state.selected!==cid)return;const detail=state.details[cid],c={...(state.courses[cid]||{code:cid,title:'Course outside this degree pool'}),...(detail||{})};const box=$('course-content');box.replaceChildren();box.append(el('h2','course-code',cid),el('h3','course-name',c.title));const meta=el('div','course-meta');if(c.credits!=null)meta.append(el('span','badge',c.credits+' SU'));if(c.ects!=null)meta.append(el('span','badge',c.ects+' ECTS'));if(c.faculty)meta.append(el('span','badge',c.faculty));box.append(meta);if(state.courses[cid]){const marks=el('div','mark-actions');marks.append(button('◇ Planned',`mark-button planned ${state.marks[cid]==='planned'?'active':''}`,()=>mark(cid,'planned')),button('✓ Completed',`mark-button completed ${state.marks[cid]==='completed'?'active':''}`,()=>mark(cid,'completed')));box.append(marks);}const prereq=el('section','course-section');prereq.append(el('h3','','Prerequisites'));const expr=el('div','requirement-expression');if(detail)drawExpression(detail.prerequisite,expr);else expr.append(text(loading?'Checking the official course page…':'Prerequisites have not been loaded. This does not mean there are none.','muted-small'));prereq.append(expr);if(detail?.prerequisiteText){const raw=el('details','raw-rule');raw.append(el('summary','','Source wording'),text(detail.prerequisiteText));prereq.append(raw);}box.append(prereq);const co=el('section','course-section');co.append(el('h3','','Corequisites · take together'));const coexpr=el('div','requirement-expression');if(detail)drawExpression(detail.corequisite,coexpr,'No corequisite listed.');else coexpr.append(text('Not loaded. Labs and recitations may be required.','muted-small'));co.append(coexpr);box.append(co);if(detail?.generalRequirements||detail?.restrictions){const general=el('section','course-section');general.append(el('h3','','Additional conditions'),text([detail.generalRequirements,detail.restrictions].filter(Boolean).join(' '),'muted-small'));box.append(general);}const forward=el('section','course-section');forward.append(el('h3','','Opens next'));const indexed=M.reverseIndex(state.details,state.courses)[cid]||[];if(indexed.length){for(const next of indexed){const line=button(next.code,'course-chip',()=>openCourse(next.code));line.append(el('small','',state.details[next.code]?.prerequisite?.type==='and'?'Other prerequisites also required':M.ruleBadge(state.details[next.code])==='OR'?'Alternative prerequisite path':''));forward.append(line);}}else forward.append(text('No outgoing links in the checked data. Unchecked courses may still depend on this one.','muted-small'));box.append(forward);appendSchedule(box,cid);box.append(button('Show what this course opens →','secondary',()=>showUnlocks(cid)));box.append(button('Review prerequisite chain','quiet wide',()=>{state.focus=cid;state.focusMode='requires';state.view='graph';closeCourse();render(true);}));const section=state.degree.sections.find(s=>s.courses.some(x=>x.code===cid));if(section){const rule=el('section','course-section');rule.append(el('h3','',section.label),text(section.rule||'Read the degree rules before selecting from this pool.','muted-small'));box.append(rule);}const source=detail?.source||c.source||`https://suis.sabanciuniv.edu/prod/sabanci_www.p_get_courses?crse_numb=${encodeURIComponent(cid.split(' ')[1])}&lang=eng&levl_code=UG&subj_code=${encodeURIComponent(cid.split(' ')[0])}`;box.append(externalLink('Open official course page ↗',source));box.append(text(detail?`${detail.origin==='bundled'?'Bundled detail':'Catalog detail'} · ${dateLabel(detail.observedAt)}${loading?' · checking for updates':''}`:loading?'Source check in progress':'No verified prerequisite detail cached','muted-small'));box.append(text(state.catalogTerm?`Prerequisites: catalog ${state.catalogTerm}. Degree categories: admission ${state.degree.term}. Offered status: Dynamic Schedule only.`:'Saved reference rules are not verified for a selected catalog term. Marks do not prove grades or registration eligibility.','muted-small'));if(error)box.append(el('div','notice-box',error));if(!detail&&!loading&&!preview)box.append(button('Check source again','secondary',()=>openCourse(cid)));}
  async function openCourse(cid){
    if(!state.degree)return;
    detailAbort?.abort();scheduleAbort?.abort();detailAbort=new AbortController();
    const signal=detailAbort.signal,token=++state.detailToken,ct=state.catalogTerm;
    lastFocus=document.activeElement;state.selected=cid;$('course-panel').hidden=false;
    $('workspace').classList.add('panel-open');$('search-results').hidden=true;
    if(!state.details[cid]){const saved=scopedSeed();if(saved[cid])state.details[cid]=saved[cid];}
    renderCourse(cid,!preview&&Boolean(ct));if(preview||!ct)return;
    try{await watch('api/course?code='+encodeURIComponent(cid)+'&catalogTerm='+encodeURIComponent(ct),result=>{
      if(token!==state.detailToken||state.selected!==cid||state.catalogTerm!==ct)return;
      if(result.data){if(result.data.code!==cid||result.data.catalogTerm!==ct)throw new Error('Course response belongs to a different catalog term.');
        state.details[cid]=result.data;render(false);}
      renderCourse(cid,Boolean(result.meta.refreshing),result.meta.error);
    },signal);}catch(error){if(error.name!=='AbortError')renderCourse(cid,false,error.message);}
  }
  function closeCourse(){detailAbort?.abort();scheduleAbort?.abort();state.selected=null;$('course-panel').hidden=true;$('workspace').classList.remove('panel-open');if(lastFocus?.isConnected&&lastFocus!==document.body)lastFocus.focus({preventScroll:true});lastFocus=null;}
  function rules(){if(!state.degree)return toast('Open a course map first.');const box=openInfo('DEGREE RULES');box.append(heading(state.degree.program.name),text(state.degree.termLabel+' · first admission term'));const total=el('div','totals-grid');for(const[n,l]of [[state.degree.total.credits,'SU credits minimum'],[state.degree.total.ects,'ECTS minimum']]){const d=el('div');d.append(el('strong','',String(n)),el('span','',l));total.append(d);}box.append(total);box.append(text('Course options are not all mandatory. Elective pools, choice rules and overlapping credit requirements must be read together.','audit-warning'));const table=el('table','summary-table');const head=el('tr');for(const v of ['CATEGORY','MIN. SU','MIN. ECTS','COURSES'])head.append(el('th','',v));table.append(head);for(const r of state.degree.summary){const tr=el('tr');for(const v of [r.label,r.credits??'·',r.ects??'·',r.courses??'·'])tr.append(el('td','',String(v)));table.append(tr);}box.append(table);for(const r of state.degree.notes){const card=el('section','rule-card');card.append(el('h3','',r.label),text(r.text));box.append(card);}box.append(externalLink('Read the official degree requirements ↗',state.degree.source));}
  function sources(){const box=openInfo('DATA & FRESHNESS');box.append(heading('Know what you are looking at.'));if(!state.degree){box.append(text(state.meta?.error||'No matching degree snapshot is loaded.'));return;}const meta=state.meta||{};box.append(text(`${state.degree.program.name} · ${state.degree.termLabel}`));const rows=[['Degree source',state.degree.origin==='bundled'?'Bundled, manually transcribed snapshot':state.degree.origin==='user-supplied-html'?'Saved official HTML supplied by the user; linked pools not included':'Official degree requirements, parsed by the server'],['Observed',dateLabel(meta.observedAt)],['Status',meta.refreshing?'Refresh in progress':meta.state||'Unknown'],['Refresh policy','Recheck on use after 12 hours. The local app indexes prerequisite details in a rate-limited background queue. A first full index takes time, not one instant request.'],['Separate clocks',`Admission ${state.degree.term} selects degree categories. Catalog ${state.catalogTerm||'saved reference'} selects prerequisite rules. Schedule ${state.scheduleTerm} supplies sections.`],['Offline coverage',`${Object.keys(state.seed.degrees).length} saved degree selections. Unversioned examples are never silently used for a selected catalog term. Missing pools and prerequisites stay unknown.`]];for(const[label,value]of rows){const card=el('div','rule-card');card.append(el('h3','',label),text(value));box.append(card);}if(meta.error)box.append(el('div','notice-box',meta.error));for(const error of state.degree.poolErrors||[])box.append(el('div','notice-box',error));box.append(text('If a refresh fails, the exact matching last-known-good snapshot stays visible with its original observation date. A failed check never makes old data look new.','audit-warning'));box.append(externalLink('Open degree source ↗',state.degree.source));for(const section of state.degree.sections.filter(s=>['core','area','free'].includes(s.id))){box.append(el('br'),externalLink(section.label+' ↗',section.source));}}
  function myPlan(){if(!state.degree)return toast('Open a course map first.');const box=openInfo('MY PLAN');box.append(heading('Your markers. Your browser.'));const counts={planned:0,completed:0};Object.values(state.marks).forEach(s=>counts[s]++);box.append(text(`${counts.planned} planned · ${counts.completed} marked completed. These are markers, not a verified degree audit.`));const actions=el('div','plan-actions');actions.append(button('Export JSON','secondary',exportPlan),button('Import JSON','secondary',()=>$('import-file').click()),button('Clear markers','secondary',()=>{if(confirm('Clear all markers for this major and admission term? Export a copy first to keep them.')){state.marks={};saveMarks();render(false);myPlan();}}));box.append(actions);if(!Object.keys(state.marks).length)box.append(text('Open a course and mark it Planned or Completed. The marks stay local, separated by major and admission term.'));for(const[cid,status]of Object.entries(state.marks).sort()){const row=el('div','plan-item');row.append(el('span','',cid),el('small','',status),button('Open','',()=>{$('info-dialog').close();openCourse(cid);}),button('Remove','',()=>{delete state.marks[cid];saveMarks();render(false);myPlan();}));box.append(row);}box.append(text('No names, grades, transcript uploads, accounts, analytics or university credentials. A live server sees requested course codes and standard HTTP connection metadata, not your markers. Export a backup before clearing browser storage.','audit-warning'));}
  function exportPlan(){if(!state.degree)return;const payload={schemaVersion:1,program:state.degree.program.id,term:state.degree.term,marks:state.marks};const blob=new Blob([JSON.stringify(payload,null,2)],{type:'application/json'});const url=URL.createObjectURL(blob);const a=el('a');a.href=url;a.download=`prereq-${payload.program}-${payload.term}-plan.json`;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),5000);}
  async function importPlan(){const file=$('import-file').files[0];$('import-file').value='';if(!file||!state.degree)return;try{if(file.size>100000)throw new Error('Plan files must be smaller than 100 KB.');const plan=M.validatePlan(JSON.parse(await file.text()),state.degree);if(Object.keys(state.marks).length&&!confirm('Replace the markers for this major and admission term with this imported plan?'))return;state.marks=plan;saveMarks();render(false);myPlan();toast('Plan imported.');}catch(error){toast(error.message||'This plan could not be imported.',true);}}
  function coverageInfo(){const box=openInfo('PREREQUISITE COVERAGE');const cv=M.coverage(state.details,state.courses);box.append(heading(`${cv.checked} of ${cv.total} courses checked`),text('Only verified, parsed prerequisite expressions create branches. An absent edge is not proof that a course opens nothing.'));box.append(text('Click a course to expand the courses that list it as a prerequisite. ALL means every listed requirement matters; OR marks alternatives. Corequisites stay separate in the details.'));if(state.indexMeta?.refreshing)box.append(text('Checking more course pages in the background. Existing map coordinates stay fixed.'));if(state.layout?.capped)box.append(text('This view reached its 1,400-node rendering limit. Collapse a few branches or search for a focused course map.','notice-box'));if(state.indexMeta?.error)box.append(text(state.indexMeta.error,'notice-box'));box.append(text(preview?'Offline file: the included links do not update automatically. Start the local Python app for live checks.':'Live checks use a shared, rate-limited cache. Failed requests keep the previous dated detail.','audit-warning'));}
  function help(){const box=openInfo('MAP CONTROLS');box.append(heading('Courses, then what they open.'));for(const[title,body]of [['Expand','Click a course row or its + to reveal directly dependent courses. The i opens details. Closing a branch preserves the camera position.'],['Move','Drag to pan. Scroll or pinch to zoom. Fit and the University / Major required / Electives shortcuts move the view only when you request it.'],['Keyboard','Press / to search, F to fit, + or − to zoom. Tab and Enter expand nodes; I opens details. Arrow keys pan the focused map.'],['Read the links','Arrows point from prerequisites to dependent courses. ALL / OR badges retain the source logic. A single incoming edge is not registration permission. University courses are displayed, not marked completed.'],['Know the scope','Requirements depend on first admission term. Prerequisites use the current catalog. Missing details stay unknown. Check the coverage counter and official sources.']]){const card=el('section','rule-card');card.append(el('h3','',title),text(body));box.append(card);}}
  function choose(){const saved=state.degree?{program:state.degree.program.id,term:state.degree.term}:null;if(saved){$('major-select').value=saved.program;$('year-select').value=saved.term.slice(0,4);$('season-select').value=saved.term.slice(4);}$('close-chooser').hidden=!state.degree;if(!$('chooser').open)$('chooser').showModal();}
  async function refresh(){if(!state.degree)return toast('Choose a major and admission term first.');if(preview)return toast('This file is an offline preview. Start the Python app to enable live source checks.',true);try{const p=state.degree.program.id,t=state.degree.term;await api(`api/refresh?program=${encodeURIComponent(p)}&term=${encodeURIComponent(t)}${state.catalogTerm?'&catalogTerm='+encodeURIComponent(state.catalogTerm):''}`,'POST');mainAbort?.abort();mainAbort=new AbortController();const token=++state.degreeToken;await watch(`api/degree?program=${encodeURIComponent(p)}&term=${encodeURIComponent(t)}`,result=>{if(token!==state.degreeToken)return;if(result.data&&validDegree(result.data,p,t))applyDegree(result.data,false);updateMeta(result.meta);},mainAbort.signal);}catch(error){if(error.name!=='AbortError')toast(error.message,true);}}
  function events(){
    document.querySelector('.brand').onclick=e=>{e.preventDefault();choose();};
    $('change-major').onclick=choose;$('empty-change').onclick=choose;$('close-chooser').onclick=()=>$('chooser').close();
    $('choose-form').onsubmit=e=>{e.preventDefault();loadDegree($('major-select').value,$('year-select').value+$('season-select').value);};
    $('jump-university').onclick=()=>jumpSection('university');$('jump-required').onclick=()=>jumpSection('required');$('jump-electives').onclick=()=>jumpSection('core');$('match-count').onclick=coverageInfo;$('rules-button').onclick=rules;$('plan-button').onclick=myPlan;$('source-button').onclick=sources;$('help-button').onclick=help;$('refresh-button').onclick=refresh;
    $('close-info').onclick=()=>$('info-dialog').close();$('close-course').onclick=closeCourse;$('import-file').onchange=importPlan;
    $('search').addEventListener('input',searchResults);$('search').addEventListener('keydown',e=>{if(e.key==='Escape')$('search-results').hidden=true;if(e.key==='Enter'){e.preventDefault();$('search-results').querySelector('button')?.click();}});
    document.addEventListener('pointerdown',e=>{if(!e.target.closest('.search-block'))$('search-results').hidden=true;});
    $('catalog-term').onchange=changeCatalog;
    $('status-filter').onchange=()=>{state.filter=$('status-filter').value;state.listLimit=100;render(false);};
    $('graph-tab').onclick=()=>{state.view='graph';render(false);};$('list-tab').onclick=()=>{state.view='list';render(false);};$('list-more').onclick=()=>{state.listLimit+=100;renderList();};
    $('back-to-degree').onclick=()=>{state.focus=null;state.focusMode='unlocks';render(true);};$('zoom-in').onclick=()=>zoom(1.2);$('zoom-out').onclick=()=>zoom(1/1.2);$('fit-button').onclick=()=>fit(true);
    $('reset-button').onclick=()=>{state.focus=null;state.focusMode='unlocks';state.query='';$('search').value='';$('search-results').hidden=true;state.filter='all';$('status-filter').value='all';state.expanded=defaultExpanded();closeCourse();render(true);};
    document.addEventListener('keydown',e=>{if($('chooser').open||$('info-dialog').open)return;const typing=/INPUT|SELECT|TEXTAREA/.test(document.activeElement?.tagName);if(e.key==='Escape'){closeCourse();$('search-results').hidden=true;return;}if(typing||e.ctrlKey||e.metaKey||e.altKey)return;if(e.key==='/'){e.preventDefault();$('search').focus();}if(e.key==='f'||e.key==='F'){e.preventDefault();fit(true);}if(e.key==='+'||e.key==='=')zoom(1.15);if(e.key==='-')zoom(1/1.15);});
    $('graph').addEventListener('keydown',e=>{const amounts={ArrowLeft:[40,0],ArrowRight:[-40,0],ArrowUp:[0,40],ArrowDown:[0,-40]};if(amounts[e.key]){e.preventDefault();state.transform.x+=amounts[e.key][0];state.transform.y+=amounts[e.key][1];transform();}});
    $('graph').addEventListener('wheel',e=>{e.preventDefault();const b=$('graph').getBoundingClientRect();zoom(Math.exp(-e.deltaY*.0016),e.clientX-b.left,e.clientY-b.top);},{passive:false});
    const points=new Map();let origin=null,pinch=null,moved=false;
    const pair=()=>{const a=[...points.values()];return {x:(a[0].x+a[1].x)/2,y:(a[0].y+a[1].y)/2,d:Math.hypot(a[0].x-a[1].x,a[0].y-a[1].y)};};
    $('graph').addEventListener('pointerdown',e=>{if(e.button>0)return;cancelAnimationFrame(cameraFrame);points.set(e.pointerId,{x:e.clientX,y:e.clientY});if(points.size===1){origin={x:e.clientX,y:e.clientY,tx:state.transform.x,ty:state.transform.y};moved=false;lastDrag=false;}else if(points.size===2){pinch=pair();moved=true;}if(!e.target.closest('[data-node]'))try{$('graph').setPointerCapture(e.pointerId);}catch{}});
    $('graph').addEventListener('pointermove',e=>{if(!points.has(e.pointerId))return;points.set(e.pointerId,{x:e.clientX,y:e.clientY});if(points.size===2){const p=pair(),b=$('graph').getBoundingClientRect();if(pinch&&pinch.d>1){zoom(p.d/pinch.d,pinch.x-b.left,pinch.y-b.top);state.transform.x+=p.x-pinch.x;state.transform.y+=p.y-pinch.y;transform();}pinch=p;moved=true;}else if(origin){const dx=e.clientX-origin.x,dy=e.clientY-origin.y;if(Math.hypot(dx,dy)>4)moved=true;if(moved){try{$('graph').setPointerCapture(e.pointerId);}catch{}state.transform.x=origin.tx+dx;state.transform.y=origin.ty+dy;transform();$('graph').classList.add('dragging');}}});
    const end=e=>{points.delete(e.pointerId);lastDrag=moved;if(points.size===1){const p=[...points.values()][0];origin={x:p.x,y:p.y,tx:state.transform.x,ty:state.transform.y};pinch=null;}if(!points.size){origin=null;pinch=null;$('graph').classList.remove('dragging');setTimeout(()=>lastDrag=false,60);}};
    $('graph').addEventListener('pointerup',end);$('graph').addEventListener('pointercancel',end);
    let lastSize=$('graph').getBoundingClientRect();window.addEventListener('resize',()=>{clearTimeout(resizeTimer);resizeTimer=setTimeout(()=>{const b=$('graph').getBoundingClientRect();if(state.degree&&state.view==='graph'){cancelAnimationFrame(cameraFrame);state.transform.x+=(b.width-lastSize.width)/2;state.transform.y+=(b.height-lastSize.height)/2;transform();}lastSize=b;},100);});
    for(const dialog of [$('chooser'),$('info-dialog')])dialog.addEventListener('click',e=>{if(e.target===dialog){const r=dialog.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom){if(dialog.id!=='chooser'||state.degree)dialog.close();}}});
    $('chooser').addEventListener('cancel',e=>{if(!state.degree)e.preventDefault();});
  }
  async function init(){try{state.seed=window.__PREVIEW_SEED__||await(await fetch('seed.json',{cache:'no-cache'})).json();state.catalogTerm=preview?null:(getLocal('prereq.catalog-term.v1')||'202601');if(state.catalogTerm==='snapshot')state.catalogTerm=null;state.details=scopedSeed();
      const savedOption=el('option','','Saved reference (unversioned)');savedOption.value='snapshot';$('catalog-term').append(savedOption);
      for(const t of state.seed.catalogTerms||[{id:'202601',label:'Fall 2026–2027'}]){const o=el('option','',t.label);o.value=t.id;$('catalog-term').append(o);}
      if(state.catalogTerm&&![...$('catalog-term').options].some(o=>o.value===state.catalogTerm))state.catalogTerm='202601';
      $('catalog-term').value=state.catalogTerm||'snapshot';if(preview)$('catalog-term').disabled=true;
      for(const p of state.seed.programs){const opt=el('option','',p.name);opt.value=p.id;$('major-select').append(opt);}const year=Math.max(2026,new Date().getFullYear());for(let y=year;y>=1999;y--){const opt=el('option','',`${y}–${y+1}`);opt.value=String(y);$('year-select').append(opt);}$('year-select').value='2024';$('chooser-note').textContent=preview?'Saved EE and partial BIO examples only. This file does not fetch live data.':'All configured majors use their own official requirements. Prerequisites use the separate Catalog selector.';events();loadCatalogTerms();let saved=null;try{saved=JSON.parse(getLocal('prereq.selection.v1'));}catch{}if(saved&&state.seed.programs.some(p=>p.id===saved.program)&&/^\d{4}0[123]$/.test(saved.term))loadDegree(saved.program,saved.term);else choose();}catch(error){$('footer-status').textContent='Could not load local data.';$('empty-state').hidden=false;$('empty-title').textContent='Open the standalone preview or start the app';$('empty-message').textContent='Run python3 start.py from the project folder. Opening web/index.html directly cannot load its data file.';$('empty-change').hidden=true;console.error(error);}}
  init();
})();
