/* Course relationships are derived only from parsed prerequisite expressions.
   A link is a prerequisite contribution, not a registration-eligibility claim. */
(function (root) {
  'use strict';
  const normal = value => String(value || '').toLowerCase().replace(/[^\p{L}\p{N}]+/gu, '');
  const compare = (a, b) => a.localeCompare(b, 'en', { numeric: true });
  const uniqueCourses = degree => Object.fromEntries(degree.sections.flatMap(s => s.courses.map(c => [c.code, c])));
  const node = (id, label, kind, children = [], extra = {}) => ({ id, label, kind, children, ...extra });
  const subject = code => String(code).split(' ')[0];
  const subjectClass = code => ({ EE:'ee',EL:'ee',BIO:'bio',CS:'cs',ME:'me',IE:'ie',MAT:'mat',DSA:'dsa' })[subject(code)] || 'other';
  function leaves(ast) {
    if (!ast || ast.type === 'unknown' || ast.type === 'none') return [];
    if (ast.type === 'course') return [{ code: ast.code, minGrade: ast.minGrade || null }];
    return (ast.children || []).flatMap(leaves);
  }
  function known(ast) {
    return Boolean(ast && (ast.type === 'none' || ast.type === 'course' ||
      ['and','or'].includes(ast.type) && ast.children?.length && ast.children.every(known)));
  }
  function expressionLabel(ast) {
    if (!known(ast)) return 'Not checked';
    if (ast.type === 'none') return 'No course prerequisite listed';
    if (ast.type === 'course') return ast.code + (ast.minGrade ? ` ≥ ${ast.minGrade}` : '');
    return '(' + ast.children.map(expressionLabel).join(ast.type === 'and' ? ' + ' : ' OR ') + ')';
  }
  function ruleBadge(detail) {
    if (!detail || !known(detail.prerequisite)) return '?';
    const ast = detail.prerequisite;
    if (ast.type === 'and') return ast.children.some(c => c.type === 'or') ? 'ALL/OR' : 'ALL';
    if (ast.type === 'or') return 'OR';
    if (detail.generalRequirements) return '!';
    return '';
  }
  function reverseIndex(details, courses) {
    const result = Object.create(null);
    for (const [cid, detail] of Object.entries(details)) {
      if (!Object.hasOwn(courses, cid) || !known(detail.prerequisite)) continue;
      // No partial parsing: an unknown conjunct cannot quietly disappear.
      for (const part of leaves(detail.prerequisite)) {
        if (!result[part.code]) result[part.code] = [];
        if (!result[part.code].some(x => x.code === cid)) result[part.code].push({code:cid,minGrade:part.minGrade});
      }
    }
    for (const list of Object.values(result)) list.sort((a,b) => compare(a.code,b.code));
    return result;
  }
  function coverage(details,courses) {
    const ids = Object.keys(courses);
    return {total:ids.length, checked:ids.filter(id=>known(details[id]?.prerequisite)).length,
      loaded:ids.filter(id=>Boolean(details[id])).length};
  }
  function sections(degree) {
    const lookup = Object.fromEntries(degree.sections.map(s => [s.id,s]));
    return [lookup.university,lookup.required,
      ...degree.sections.filter(s=>!['university','required','core','area','free'].includes(s.id)),
      lookup.core,lookup.area,lookup.free].filter(Boolean);
  }
  function choicesFor(degree, section) {
    return (degree.choices || []).filter(c => section.id === 'university' && c.id === 'hum' || section.id === 'required' && c.id === 'math');
  }
  /* Build only the visible tree. Closed paths never materialize thousands of
     duplicate descendants, and repeated courses retain distinct stable path IDs. */
  function forwardForest(degree, details, expanded, marks = {}, options = {}) {
    const courses = uniqueCourses(degree), index = reverseIndex(details,courses);
    const rows = [], edges = [], groups = [], query = normal(options.query);
    const ROW = 38, COLUMN = 360, MAX_NODES = 1400, MAX_DEPTH = 12;
    let cursor = 0, capped = false;
    function add(n, parent = null, edgeKind = 'prerequisite') {
      rows.push(n);
      if (parent) edges.push({id:`${parent.id}>${n.id}`,from:parent,to:n,kind:edgeKind,minGrade:n.minGrade});
      return n;
    }
    function visit(cid, id, depth, parent, ancestry, extra = {}) {
      if (rows.length >= MAX_NODES) { capped=true; return; }
      const c = courses[cid] || details[cid] || {code:cid,title:'Outside this degree pool'};
      const children = index[cid] || [], cycle = ancestry.has(cid), limited = depth >= MAX_DEPTH;
      const n = add({id,label:cid,kind:'course',course:c,x:depth*COLUMN,y:cursor,width:250,depth,
        subtitle:c.title,count:children.length,expandable:children.length>0&&!cycle&&!limited,
        open:expanded.has(id),minGrade:extra.minGrade,sourceCode:parent?.course?.code,
        subjectClass:subjectClass(cid),badge:ruleBadge(details[cid]),
        section:extra.section||parent?.section,cycle,limited,
        matched:!query||normal(cid+' '+c.title).includes(query),
        statusMatch:!options.status||options.status==='all'||(marks[cid]||'unmarked')===options.status},parent);
      cursor += ROW;
      if (!n.expandable || !n.open) return n;
      const seen = new Set(ancestry); seen.add(cid);
      const start = cursor;
      cursor = n.y;
      for (const child of children) visit(child.code,`${id}>${child.code}`,depth+1,n,seen,{minGrade:child.minGrade});
      cursor = Math.max(start,cursor) + 10;
      return n;
    }
    if (options.focus) {
      const h=add({id:'section:focus',label:`${options.focus} · unlocks`,kind:'section',x:0,y:cursor,width:250,count:index[options.focus]?.length||0,open:true,expandable:false});
      groups.push(h);cursor+=48;
      visit(options.focus,`focus:${options.focus}`,0,null,new Set());
    } else {
      for (const section of sections(degree)) {
        if(rows.length>=MAX_NODES){capped=true;break;}
        const title = {university:'University courses',required:'Major required',core:'Core electives',area:'Area electives',free:'Free electives'}[section.id] || section.label;
        const sid=`section:${section.id}`, open=expanded.has(sid);
        const h=add({id:sid,label:title,kind:'section',x:0,y:cursor,width:250,section:section.id,
          count:section.courses.length,open,expandable:section.courses.length>0,rule:section.rule});
        groups.push(h); cursor+=open?48:62;
        if (!open) continue;
        const choices=choicesFor(degree,section), choiceCodes=new Set(choices.flatMap(c=>c.codes||c.options?.flat()||[]));
        // Keep course order from the official degree page; no subject folders or ranges.
        for (const c of section.courses.filter(c=>!choiceCodes.has(c.code))) {
          visit(c.code,`${sid}/${c.code}`,0,null,new Set(),{section:section.id});
        }
        for (const choice of choices) {
          if(rows.length>=MAX_NODES){capped=true;break;}
          const id=`choice:${choice.id}`, chOpen=expanded.has(id);
          const codes=choice.codes||choice.options?.flat()||[];
          const n=add({id,label:choice.id==='hum'?'HUM · choose one':'MATH · choose a path',kind:'choice',
            x:0,y:cursor,width:250,count:codes.length,open:chOpen,expandable:true,section:section.id,
            subtitle:choice.id==='math'?'MATH 212 OR (201 + 202)':'One course, not all options'});
          cursor+=ROW+8;
          if(chOpen) for (const cid of codes) if(courses[cid]) {
            const child=visit(cid,`${id}/${cid}`,0,null,new Set(),{section:section.id});
            if(child) child.choice=true;
          }
        }
        cursor+=38;
      }
    }
    return {nodes:rows,edges,groups,width:Math.max(300,...rows.map(n=>n.x+n.width+20)),
      height:cursor+25,index,coverage:coverage(details,courses),capped};
  }
  // The secondary upstream view preserves full AND / OR logic for source review.
  function dependencyTree(cid, details, courses) {
    function expression(ast, depth, seen, path) {
      if (!ast || ast.type === 'unknown') return node(path,'Needs source check','notice',[],{subtitle:ast?.reason||'Check this course source'});
      if (ast.type === 'none') return null;
      if (ast.type === 'course') return visit(ast.code,depth,seen,path,ast.minGrade);
      return node(path,ast.type === 'and'?'ALL of':'ANY of','logic',(ast.children||[]).map((a,i)=>expression(a,depth,seen,`${path}/${i}`)).filter(Boolean));
    }
    function visit(value,depth,seen,path,grade) {
      const d=details[value],c=courses[value]||d||{code:value,title:'Outside this degree pool'};
      const n=node(path,value,'course',[],{course:c,subtitle:c.title,minGrade:grade,subjectClass:subjectClass(value)});
      if(seen.has(value)){n.children=[node(path+'/cycle','Cycle in source','notice')];return n;}
      if(depth>=12){n.children=[node(path+'/limit','Depth limit','notice')];return n;}
      if(!d){n.children=[node(path+'/load','Check prerequisite source','load',[],{code:value})];return n;}
      const next=new Set(seen);next.add(value);const child=expression(d.prerequisite,depth+1,next,path+'/rule');
      if(child)n.children=[child];return n;
    }
    return visit(cid,0,new Set(),`requires:${cid}`);
  }
  function layout(rootNode,expanded) {
    const nodes=[],edges=[];let cursor=0;
    function walk(n,depth,parent){
      const view={...n,x:depth*360,y:cursor,width:250,depth,open:true,expandable:false};nodes.push(view);
      if(n.children.length){for(const child of n.children)walk(child,depth+1,view);}else cursor+=46;
      if(parent)edges.push({id:`${parent.id}>${view.id}`,from:parent,to:view,kind:'requires'});
      return view;
    }
    walk(rootNode,0,null);
    return {nodes,edges,groups:[],width:Math.max(...nodes.map(n=>n.x+n.width)),height:cursor+30};
  }
  function validatePlan(value,degree) {
    if(!value||value.schemaVersion!==1||value.program!==degree.program.id||value.term!==degree.term||!value.marks||typeof value.marks!=='object'||Array.isArray(value.marks))throw new Error('Choose a version-1 plan for this exact major and admission term.');
    const knownCourses=uniqueCourses(degree),entries=Object.entries(value.marks);
    if(entries.length>1500)throw new Error('Plan is too large.');
    const result=Object.create(null);
    for(const [cid,status] of entries){if(!Object.hasOwn(knownCourses,cid)||!['planned','completed'].includes(status))throw new Error('Plan contains an unknown course or status. Nothing was imported.');result[cid]=status;}
    return result;
  }
  const api={normal,uniqueCourses,subjectClass,leaves,known,expressionLabel,ruleBadge,reverseIndex,coverage,sections,forwardForest,dependencyTree,layout,validatePlan};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;
  root.PrereqModel=Object.freeze(api);
})(typeof globalThis!=='undefined'?globalThis:this);
