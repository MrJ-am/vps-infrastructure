// Deux bases indépendantes, rôle applicatif non propriétaire, données synthétiques.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdtempSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {resolve,join} from 'node:path';
import {pathToFileURL} from 'node:url';
import {spawnSync} from 'node:child_process';
const root=resolve(process.env.MRJAM_ATELIER||'..');
const base=process.env.TEST_DATABASE_URL||'postgres://postgres@127.0.0.1:55432/postgres';
const url=new URL(base);
assert.equal(url.hostname,'127.0.0.1','Tests strictement locaux');
assert.equal(url.username,'postgres','Compte réservé au montage de la fixture');
const {connect,migrate,importCorpus,digest}=await import(pathToFileURL(join(root,'M-moire/server/src/database.mjs')));
const {createApp}=await import(pathToFileURL(join(root,'M-moire/server/src/app.mjs')));
const {prepareSession}=await import(pathToFileURL(join(root,'M-moire/docs/site/session.js')));
const bank=JSON.parse(readFileSync(join(root,'M-moire/research/bank.json'),'utf8'));
const codes=JSON.parse(readFileSync(join(root,'M-moire/research/codebook.json'),'utf8'));
const admin=connect(base),suffix=String(process.pid),role='matheval_app_'+suffix;
const names=['matheval_reference_'+suffix+'_test','matheval_lisp_'+suffix+'_test',
 ...(process.env.MRJAM_TEST_EXECUTABLE?['matheval_artefact_'+suffix+'_test']:[])];
const temp=mkdtempSync(join(tmpdir(),'matheval-composant-'));
const keep=!!process.env.MRJAM_FIXTURES;let pool,server;
const normalized=v=>Array.isArray(v)?v.map(normalized):v&&typeof v==='object'?Object.fromEntries(Object.entries(v).map(([k,x])=>[k,['startedAt','completedAt','savedAt','started_at','updated_at','completed_at','imported_at'].includes(k)&&x!==null?'<date>':normalized(x)])):v;
try {
 await admin.query(`CREATE ROLE ${role} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS`);
 for(const name of names) {
  await admin.query(`CREATE DATABASE ${name}`);
  const u=new URL(base);u.pathname='/'+name;const p=connect(u.href);
  try {await migrate(p);
   await p.query(`REVOKE CREATE ON SCHEMA public FROM PUBLIC; GRANT USAGE ON SCHEMA public TO ${role}; GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA public TO ${role}; GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA public TO ${role}`);
   await importCorpus(p,bank,codes);
  } finally {await p.end();}
 }
 const u=new URL(base);u.pathname='/'+names[0];u.username=role;pool=connect(u.href);
 const setup='f'.repeat(64),origin='http://127.0.0.1:4173',cookies={},cases=[];
 const app=createApp({pool,origin,setupHash:digest(setup),currentVersion:bank.version,testMode:true});
 server=app.listen(0,'127.0.0.1');await new Promise(r=>server.once('listening',r));
 const endpoint=`http://127.0.0.1:${server.address().port}/matheval/api`;
 async function request(path,{method='GET',data,secret,cookieRef,setCookie,foreign=false,correction}={}) {
  const headers={'Content-Type':'application/json',Origin:foreign?'https://foreign.invalid':origin,'X-Matheval-Request':'1',...(secret?{'X-Session-Token':secret}:{})};
  const response=await fetch(endpoint+path,{method,headers:{...headers,...(cookieRef?{Cookie:cookies[cookieRef]}:{})},...(data?{body:JSON.stringify(data)}:{})});
  const body=response.headers.get('content-type')?.includes('json')?await response.json():await response.text();
  if(setCookie){const c=response.headers.get('set-cookie');assert.ok(c);assert.match(c,/HttpOnly/);assert.match(c,/SameSite=Strict/);cookies[setCookie]=c.split(';')[0];}
  if(correction) assert.equal(response.status,correction.ancien);
  cases.push({path,method,data:data?structuredClone(data):null,headers,cookieRef:cookieRef||null,setCookie:setCookie||null,
    expected:{status:correction?correction.nouveau:response.status,body:correction?{error:correction.message}:normalized(body)}});
  return body;
 }
 const id='13579abc-4321-4567-89ab-13579abc4321',secret='a'.repeat(64),levels=[bank.questions[0].level];
 const create={id,secret,bankVersion:bank.version,levels,seed:4294967295};
 const q=prepareSession(bank,levels,create.seed)[0],p=q.productions[0];
 const checkpoint={revision:1,final:false,snapshot:{answers:{[p.id]:{note:0,initialNote:1,coordinates:{x:0.10000000000000002,y:-3.141592653589793,z:0},evaluatedAxes:['x']}},skippedQuestions:[],progress:{mode:'running',index:0,selected:p.id,exposed:{[q.id]:1},reader:false,tour:-1}},events:[{event:'grade',questionId:q.id,productionId:p.id,at:'2026-09-16T10:00:00.000Z',elapsedMs:200,value:0,initial:true}]};
 await request('/health');await request('/admin/statistics');await request('/admin/participations/invalide');
 await request('/admin/setup',{method:'POST',data:{token:setup,username:'science',password:'mot-de-passe-test-synthetique'},foreign:true});
 await request('/sessions',{method:'POST',data:create});await request('/sessions',{method:'POST',data:create});
 await request('/sessions',{method:'POST',data:{...create,secret:'b'.repeat(64)}});
 await request('/sessions',{method:'POST',data:{...create,seed:1}});
 await request('/sessions/'+id,{secret:'b'.repeat(64)});await request('/sessions/'+id,{secret});
 await request('/sessions/11111111-1111-0111-0111-111111111111',{secret});
 await request('/sessions/------------------------------------',{secret,correction:{ancien:500,nouveau:404,message:'Participation introuvable.'}});
 await request('/sessions/'+id,{method:'PUT',data:checkpoint,secret});
 await request('/sessions/'+id,{method:'PUT',data:checkpoint,secret});
 await request('/sessions/'+id,{secret});await request('/sessions/'+id+'/events',{secret});
 const modified=structuredClone(checkpoint);modified.snapshot.answers[p.id].note=2;
 await request('/sessions/'+id,{method:'PUT',data:modified,secret});modified.revision=2;modified.events[0].value=2;
 await request('/sessions/'+id,{method:'PUT',data:modified,secret});
 const second=structuredClone(checkpoint);second.revision=2;second.events.push({...second.events[0],event:'place',elapsedMs:300,coordinates:{x:1e-7,y:2,z:0}});
 await request('/sessions/'+id,{method:'PUT',data:second,secret});
 await request('/sessions/'+id,{method:'PUT',data:{...second,revision:3,events:[]},secret});
 const last=structuredClone(second);last.revision=3;last.final=true;last.snapshot.progress.mode='finished';
 await request('/sessions/'+id,{method:'PUT',data:last,secret});await request('/sessions/'+id,{method:'PUT',data:last,secret});
 await request('/sessions/'+id,{method:'PUT',data:{...last,revision:4,final:false},secret});
 const activation={token:setup,username:'science',password:'mot-de-passe-test-synthetique'};
 await request('/admin/setup',{method:'POST',data:activation,setCookie:'admin1'});
 await request('/admin/setup',{method:'POST',data:activation});
 await request('/admin/login',{method:'POST',data:{username:'absent',password:'mauvais'}});
 await request('/admin/me',{cookieRef:'admin1'});await request('/admin/corpora',{cookieRef:'admin1'});
 await request('/admin/corpus/'+bank.version,{cookieRef:'admin1'});
 await request('/admin/statistics?status=completed',{cookieRef:'admin1'});
 await request('/admin/statistics?level=inconnu',{cookieRef:'admin1'});
 await request('/admin/statistics?from=2026-02-30',{cookieRef:'admin1',correction:{ancien:500,nouveau:400,message:'Données invalides. Vérifiez les champs et réessayez.'}});
 await request('/admin/participations?status=completed',{cookieRef:'admin1'});
 await request('/admin/participations/'+id,{cookieRef:'admin1'});
 await request('/admin/productions/'+p.id+'/answers',{cookieRef:'admin1'});
 // CSV contient des dates réelles différentes ; sa structure/échappement sont
 // comparés exactement dans les tests purs, ici statut/type et contenu privé.
 await request('/admin/login',{method:'POST',data:{username:activation.username,password:activation.password},cookieRef:'admin1',setCookie:'admin2'});
 await request('/admin/me',{cookieRef:'admin1'});await request('/admin/me',{cookieRef:'admin2'});
 await request('/admin/logout',{method:'POST',data:{},cookieRef:'admin2'});await request('/admin/me',{cookieRef:'admin2'});
 const empreintes=(await pool.query('SELECT payload_hash,token_hash FROM participations WHERE id=$1',[id])).rows[0];
 const corpusDigest=(await pool.query('SELECT digest FROM corpus WHERE version=$1',[bank.version])).rows[0].digest;
 const fixture={connexion:`host=127.0.0.1 port=${url.port||5432} user=${role} dbname=${names[1]}`,activation:digest(setup),version:bank.version,
  id,empreintes,corpusDigest,bankPath:join(root,'M-moire/research/bank.json'),codebookPath:join(root,'M-moire/research/codebook.json'),cases};
 const path=process.env.MRJAM_FIXTURES||join(temp,'cas.json');writeFileSync(path,JSON.stringify(fixture));
 if(keep) console.log(`${cases.length} parcours préparés, base isolée ${names[1]}.`);
 else {
  const lit=s=>'"'+s.replaceAll('\\','\\\\').replaceAll('"','\\"')+'"';
  writeFileSync(join(temp,'runner.lisp'),`(load ${lit(resolve('assemblage/charger.lisp'))})\n(asdf:load-system "mrjam-metier")\n(mrjam-native:initialiser-crypto ${lit(process.env.MRJAM_LIBCRYPTO||'/lib/x86_64-linux-gnu/libcrypto.so.3')})\n(mrjam-native:initialiser-postgresql ${lit(process.env.MRJAM_LIBPQ||'/lib/x86_64-linux-gnu/libpq.so.5')})\n(load ${lit(resolve('tests/matheval-composant.lisp'))})\n(matheval-composant:verifier ${lit(path)})`);
  const result=spawnSync(process.env.SBCL||'sbcl',['--script',join(temp,'runner.lisp')],{encoding:'utf8',maxBuffer:1024*1024});
  process.stdout.write(result.stdout||'');process.stderr.write(result.stderr||'');assert.equal(result.status,0,'Différence HTTP/transactions');
  console.log(`${cases.length} parcours différentiels HTTP/transactions réussis.`);
  if(process.env.MRJAM_TEST_EXECUTABLE) {
   const artefactFixture={...fixture,connexion:`host=127.0.0.1 port=${url.port||5432} user=${role} dbname=${names[2]}`};
   const artefactPath=join(temp,'artefact.json');writeFileSync(artefactPath,JSON.stringify(artefactFixture));
   const a=spawnSync('python3',['tests/serveur-artefact.py','--executable',process.env.MRJAM_TEST_EXECUTABLE,'--fixture',artefactPath],{encoding:'utf8',maxBuffer:1024*1024});
   process.stdout.write(a.stdout||'');process.stderr.write(a.stderr||'');assert.equal(a.status,0,'Qualification du binaire servi');
  }
 }
} finally {
 if(server) await new Promise(r=>server.close(r));if(pool)await pool.end();
 for(const name of names) if(!keep||name===names[0]) await admin.query(`DROP DATABASE IF EXISTS ${name}`);
 if(!keep)await admin.query(`DROP ROLE ${role}`);
 await admin.end();rmSync(temp,{recursive:true,force:true});
}
