// Référence réelle JavaScript, données exclusivement synthétiques/corpus public.
import assert from 'node:assert/strict';
import { readFileSync, mkdtempSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { spawnSync } from 'node:child_process';
import { pathToFileURL } from 'node:url';
const root = resolve(process.env.MRJAM_ATELIER || '..');
const {randomFrom, prepareSession} = await import(pathToFileURL(join(root,'M-moire/docs/site/session.js')));
const {summary, summarizeAnswers, csv} = await import(pathToFileURL(join(root,'M-moire/server/src/statistics.mjs')));
const {newParticipation, checkpoint, validateCheckpoint} = await import(pathToFileURL(join(root,'M-moire/server/src/validation.mjs')));
const bank=JSON.parse(readFileSync(join(root,'M-moire/research/bank.json'),'utf8'));
const niveaux=[...new Set(bank.questions.map(q=>q.level))];
const cas=[];
for(const seed of [0,1,2,17,12345,2147483647,2147483648,4294967295]) {
 const r=randomFrom(seed);
 cas.push({op:'random',seed,expected:Array.from({length:1000},()=>r()*4294967296)});
 for(const levels of [niveaux,...niveaux.map(x=>[x])]) {
  const q=prepareSession(bank,levels,seed);
  cas.push({op:'session',seed,levels,expected:q.map(x=>({id:x.id,productions:x.productions.map(p=>p.id)}))});
 }
}
for(const values of [[],[null,0],[0,1,2,3],[0,0,0],[1.25,2.75,null,0]])
 cas.push({op:'summary',values,expected:summary(values)});
const rows=[{participation_id:'synthetique',bank_version:'1',started_at:'2026-01-01T00:00:00.000Z',completed_at:null,levels:['=HYPERLINK("test")'],question_id:'R01',production_id:'R01-1',note:0,initial_note:1,x:0,y:5,z:0,evaluated_axes:['x']},
{participation_id:'synthetique',bank_version:'1',started_at:'2026-01-01T00:00:00.000Z',completed_at:null,levels:['5e'],question_id:'R01',production_id:'R01-2',note:null,initial_note:null,x:0,y:0,z:0,evaluated_axes:[]}];
cas.push({op:'answers',rows,expected:summarizeAnswers(rows)});
cas.push({op:'csv',rows,expected:csv(rows.map(r=>({...r,started_at:new Date(r.started_at)})))});
const participation={id:'13579abc-4321-4567-89ab-13579abc4321',secret:'a'.repeat(64),bankVersion:bank.version,levels:[niveaux[0]],seed:4294967295};
function validation(op,data,schema) {const r=schema.safeParse(data);cas.push({op,data,expected:r.success?r.data:{refus:true}});}
validation('participation',participation,newParticipation);
for(const [k,values] of Object.entries({seed:[-1,4294967296,1.5,null,0],secret:['', 'A'.repeat(64)],id:['bad','00000000-0000-0000-0000-000000000000','ffffffff-ffff-ffff-ffff-ffffffffffff'],levels:[[],['x'.repeat(31)],['😀'.repeat(16)]]}))
 for(const v of values) validation('participation',{...participation,[k]:v},newParticipation);
validation('participation',{...participation,extra:true},newParticipation);
const question=prepareSession(bank,participation.levels,participation.seed)[0];
const answer={note:0,initialNote:1,coordinates:{x:0,y:-9,z:10},evaluatedAxes:['x','y']};
const save={revision:1,final:false,snapshot:{answers:{[question.productions[0].id]:answer},skippedQuestions:[],progress:{mode:'running',index:0,selected:question.productions[0].id,exposed:{[question.id]:1},reader:false,tour:-1}},events:[{event:'grade',questionId:question.id,productionId:question.productions[0].id,at:'2026-09-16T10:00:00.000Z',elapsedMs:200,value:0,initial:true}]};
validation('checkpoint',save,checkpoint);
for(const at of ['2024-02-29T23:59Z','2023-02-29T00:00:00Z','2026-09-16T10:00:00+00:00','2026-09-16T24:00:00Z','2026-09-16T10:00:00.0000001Z'])
 validation('checkpoint',{...save,events:[{...save.events[0],at}]},checkpoint);
for(const note of [null,0,0.25,0.3,3,3.25]) validation('checkpoint',{...save,snapshot:{...save.snapshot,answers:{[question.productions[0].id]:{...answer,note}}}},checkpoint);
for(const evaluatedAxes of [[],['x','x'],['z'],['none']]) validation('checkpoint',{...save,snapshot:{...save.snapshot,answers:{[question.productions[0].id]:{...answer,evaluatedAxes}}}},checkpoint);
const order=prepareSession(bank,participation.levels,participation.seed).map(q=>q.id);
for(const patch of [{},{final:true},{snapshot:{...save.snapshot,progress:{...save.snapshot.progress,index:19}}},{snapshot:{...save.snapshot,skippedQuestions:[question.id,question.id]}},{events:[{...save.events[0],questionId:'R99'}]},{events:[save.events[0],{...save.events[0],elapsedMs:199}]}]) {
 const data={...save,...patch};let expected;
 try {validateCheckpoint(data,{question_order:order},bank);expected=true;} catch {expected=false;}
 cas.push({op:'rattachements',data,order,expected});
}
const temp=mkdtempSync(join(tmpdir(),'matheval-differentiel-'));
try {
 if(process.env.MRJAM_FIXTURES) {
  writeFileSync(process.env.MRJAM_FIXTURES,JSON.stringify(cas));
  console.log(`${cas.length} cas préparés pour l'image interactive.`);
  process.exitCode=0;
 } else {
 writeFileSync(join(temp,'cas.json'),JSON.stringify(cas));
 // Les chemins ne viennent que de l'atelier ; JSON.stringify produit des littéraux
 // compatibles Lisp pour ces chemins, aucun passage par un shell.
 const literal=s=>'"'+s.replaceAll('\\','\\\\').replaceAll('"','\\"')+'"';
 writeFileSync(join(temp,'runner.lisp'),`(load ${literal(resolve('assemblage/charger.lisp'))})
(asdf:load-system "mrjam-metier")
(asdf:load-system "matheval/tests")
(matheval-tests:verifier)
(load ${literal(resolve('tests/matheval-differentiel.lisp'))})
(matheval-differentiel:verifier ${literal(join(temp,'cas.json'))} ${literal(join(root,'M-moire/research/bank.json'))})`);
 const p=spawnSync(process.env.SBCL || 'sbcl',['--script',join(temp,'runner.lisp')],{encoding:'utf8',maxBuffer:2*1024*1024});
 process.stdout.write(p.stdout||'');process.stderr.write(p.stderr||'');
 if(p.error) throw p.error;
 assert.equal(p.status,0,'Différence Lisp/JavaScript ou exécution refusée');
 console.log(`${cas.length} cas différentiels, 8000 tirages bruts et ordres complets du corpus vérifiés.`);
 }
} finally {rmSync(temp,{recursive:true,force:true});}
