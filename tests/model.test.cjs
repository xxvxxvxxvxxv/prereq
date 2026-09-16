const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const M=require('../web/model.js');
const seed=JSON.parse(fs.readFileSync(require('node:path').join(__dirname,'../web/seed.json'),'utf8'));
const degree=seed.degrees['BSEE:202401'],courses=M.uniqueCourses(degree),details=seed.details;
const open=()=>new Set(['section:university','section:required']);
const forest=(expanded=open(),options={})=>M.forwardForest(degree,details,expanded,{},options);
const flatten=n=>[n,...n.children.flatMap(flatten)];

test('624 unique degree options preserve exact published section counts',()=>{assert.equal(Object.keys(courses).length,624);assert.deepEqual(degree.sections.map(s=>s.courses.length),[24,15,39,140,406]);});
test('university, major required, core electives, area, free in that order',()=>assert.deepEqual(M.sections(degree).map(s=>s.id),['university','required','core','area','free']));
test('opening initial sections displays actual required courses',()=>{const g=forest();assert.ok(g.nodes.some(n=>n.label==='IF 100'));assert.ok(g.nodes.some(n=>n.label==='EE 202'));assert.equal(g.nodes.find(n=>n.id==='section:area').open,false);});
test('no subject folders or arbitrary number-range groups',()=>{const s=open();s.add('section:core');const g=forest(s);assert.ok(g.nodes.filter(n=>n.kind==='course').length>50);assert.ok(g.nodes.every(n=>['course','choice','section'].includes(n.kind)));assert.ok(!g.nodes.some(n=>n.kind!=='course'&&n.label==='EE'));});
test('only genuine HUM and MATH degree choices are grouped',()=>{const g=forest();assert.deepEqual(g.nodes.filter(n=>n.kind==='choice').map(n=>n.id),['choice:hum','choice:math']);assert.ok(!g.nodes.some(n=>n.label==='HUM 207'));});
test('opening the HUM choice does not mark every option required or completed',()=>{const s=open();s.add('choice:hum');const g=forest(s);assert.equal(g.nodes.filter(n=>n.choice&&n.label.startsWith('HUM ')).length,9);});
test('forward direction IF 100 to CS 201 to CS 204',()=>{const s=open();s.add('section:university/IF 100');s.add('section:university/IF 100>CS 201');const g=forest(s);const e=g.edges.find(e=>e.from.label==='CS 201'&&e.to.label==='CS 204');assert.ok(e);assert.ok(e.to.x>e.from.x);});
test('MATH 101 branches into known dependants, not every math course',()=>{const s=open();s.add('section:university/MATH 101');const targets=forest(s).edges.filter(e=>e.from.label==='MATH 101').map(e=>e.to.label);assert.deepEqual(targets,['ENS 211','MATH 102']);});
test('no fabricated section-to-course prerequisite edges',()=>assert.equal(forest().edges.length,0));
test('opening course keeps its own world position unchanged',()=>{const s=open();const a=forest(s).nodes.find(n=>n.label==='EE 202');s.add(a.id);const b=forest(s).nodes.find(n=>n.id===a.id);assert.deepEqual([a.x,a.y],[b.x,b.y]);});
test('closed paths contain no hidden descendant nodes',()=>{const g=forest();assert.ok(!g.nodes.some(n=>n.id.includes('>')));});
test('corequisites do not become prerequisite arrows',()=>{const index=M.reverseIndex(details,courses);assert.ok(!index['EE 200'].some(c=>c.code==='EE 202'));assert.ok(index['ENS 203'].some(c=>c.code==='EE 202'));});
test('unknown conjunctions do not create partial inferred edges',()=>{const d={'EE 202':{prerequisite:{type:'and',children:[{type:'course',code:'ENS 203'},{type:'unknown'}]}}};assert.deepEqual(Object.keys(M.reverseIndex(d,courses)),[]);});
test('AND, OR and mixed conditions remain distinguishable',()=>{assert.equal(M.ruleBadge(details['EE 306']),'ALL');assert.equal(M.ruleBadge(details['EE 303']),'OR');assert.equal(M.ruleBadge(details['EE 401']),'ALL/OR');assert.equal(M.ruleBadge(details['ENS 491']),'?');});
test('current detail count and fail-closed context are explicit',()=>{assert.equal(Object.keys(details).length,57);assert.deepEqual(M.coverage(details,courses),{total:624,checked:56,loaded:57});assert.equal(details['ENS 491'].prerequisite.type,'unknown');});
test('subject colors classify only by actual code prefix',()=>{assert.deepEqual(['EE 202','BIO 301','CS 204','ME 301','MATH 101'].map(M.subjectClass),['ee','bio','cs','me','other']);});
test('search retains structure; matches are not represented as eligibility',()=>{const base=forest(),searched=forest(open(),{query:'EE202'});assert.deepEqual(base.nodes.map(n=>n.id),searched.nodes.map(n=>n.id));assert.equal(searched.nodes.find(n=>n.label==='EE 202').matched,true);assert.equal(searched.nodes.find(n=>n.label==='MATH 101').matched,false);});
test('focus map opens selected course without subject categories',()=>{const g=forest(new Set(['focus:EE 202']),{focus:'EE 202'});assert.equal(g.groups.length,1);assert.ok(g.edges.some(e=>e.from.label==='EE 202'&&e.to.label==='EE 303'));});
test('same course may occur in multiple branches with unique stable IDs',()=>{const s=open();s.add('section:university/MATH 101');const g=forest(s);assert.equal(g.nodes.filter(n=>n.label==='MATH 102').length,2);assert.equal(new Set(g.nodes.map(n=>n.id)).size,g.nodes.length);});
test('cycle detection bounds an inconsistent source graph',()=>{const d={'CS 201':{prerequisite:{type:'course',code:'CS 204'}},'CS 204':{prerequisite:{type:'course',code:'CS 201'}}};const s=new Set(['focus:CS 201','focus:CS 201>CS 204','focus:CS 201>CS 204>CS 201']);const g=M.forwardForest(degree,d,s,{}, {focus:'CS 201'});assert.equal(g.nodes.filter(n=>n.cycle).length,1);assert.equal(g.nodes.filter(n=>n.cycle)[0].expandable,false);assert.ok(g.nodes.length<6);});
test('secondary upstream view preserves full mixed AND/OR tree',()=>{const nodes=flatten(M.dependencyTree('EE 401',details,courses));assert.ok(nodes.some(n=>n.label==='ALL of'));assert.ok(nodes.some(n=>n.label==='ANY of'));assert.ok(nodes.some(n=>n.minGrade==='D'));});
test('valid plans remain major- and admission-term-specific',()=>{const good={schemaVersion:1,program:'BSEE',term:'202401',marks:{'EE 202':'planned'}};assert.equal(M.validatePlan(good,degree)['EE 202'],'planned');assert.throws(()=>M.validatePlan({...good,term:'202601'},degree));assert.throws(()=>M.validatePlan({...good,program:'BSCS'},degree));});
test('plans reject unknown courses, arbitrary statuses and prototype keys',()=>{for(const marks of [{'EE 999':'completed'},{'EE 202':'eligible'},JSON.parse('{"__proto__":"planned"}')])assert.throws(()=>M.validatePlan({schemaVersion:1,program:'BSEE',term:'202401',marks},degree));});
test('catalog text stays model data, never evaluated markup',()=>{const n=M.normal('<img src=x onerror=alert(1)>');assert.equal(typeof n,'string');assert.ok(n.includes('onerror'));});


test('empty expanded set renders only five closed sections and no course edges',()=>{
  const g=forest(new Set());
  assert.deepEqual(g.nodes.map(n=>n.id),['section:university','section:required','section:core','section:area','section:free']);
  assert.ok(g.nodes.every(n=>n.kind==='section' && n.open===false));
  assert.equal(g.edges.length,0);
});
test('opening a section does not automatically expand any course or another section',()=>{
  const g=forest(new Set(['section:university']));
  assert.equal(g.nodes.find(n=>n.id==='section:required').open,false);
  assert.ok(g.nodes.filter(n=>n.kind==='course').every(n=>!n.open));
  assert.equal(g.edges.length,0);
});
