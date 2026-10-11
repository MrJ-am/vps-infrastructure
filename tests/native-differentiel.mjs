import assert from 'node:assert/strict';
import {createHash,scryptSync} from 'node:crypto';
import {readFileSync,writeFileSync,mkdtempSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join,resolve} from 'node:path';
import {spawnSync} from 'node:child_process';
const cases=[];
for(const text of ['', 'abc','élément 😀\u0000fin']) cases.push({op:'sha256',text,expected:createHash('sha256').update(text).digest('hex')});
const password='mot-é😀-de-passe-synthétique',salt='0123456789abcdef0123456789abcdef';
cases.push({op:'scrypt',password,salt,expected:scryptSync(password,salt,64,{N:131072,r:8,p:1,maxmem:256*1024*1024}).toString('hex')});
for(const input of ['[-0,0,0.25,0.10000000000000002,1e23,1e-7,1e-6,1e20,1e21,1000000000000000128,5e-324,1e-999]',
'{"a":1,"12":2,"3":3,"01":4,"0":5,"4294967295":6,"4294967294":7,"😀":"\\u000b\\u001f\\n"}'])
 cases.push({op:'json',input,expected:JSON.stringify(JSON.parse(input))});
// Bits déterministes, aucun tirage de secret : large domaine binaire64 et
// coordonnées usuelles, références natives JavaScript.
let state=123456789;const random=()=>{state^=state<<13;state^=state>>>17;state^=state<<5;return state>>>0;};
const bits=new DataView(new ArrayBuffer(8));
for(let i=0;i<4000;i++){
 bits.setUint32(0,random());bits.setUint32(4,random());const n=bits.getFloat64(0);
 if(Number.isFinite(n)) {const input=JSON.stringify(n);cases.push({op:'json',input,expected:input});}
 const x=(random()/4294967296-.5)*20;cases.push({op:'json',input:JSON.stringify(x),expected:JSON.stringify(x)});
}
const temp=mkdtempSync(join(tmpdir(),'native-differentiel-'));
try {
 const fixture=process.env.MRJAM_FIXTURES||join(temp,'cas.json');writeFileSync(fixture,JSON.stringify(cases));
 if(process.env.MRJAM_FIXTURES) console.log(`${cases.length} cas natifs préparés.`);
 else {
  const lit=s=>'"'+s.replaceAll('\\','\\\\').replaceAll('"','\\"')+'"';
  writeFileSync(join(temp,'runner.lisp'),`(load ${lit(resolve('assemblage/charger.lisp'))})\n(asdf:load-system "mrjam-native")\n(mrjam-native:initialiser-crypto ${lit(process.env.MRJAM_LIBCRYPTO||'/lib/x86_64-linux-gnu/libcrypto.so.3')})\n(load ${lit(resolve('tests/native-differentiel.lisp'))})\n(native-differentiel:verifier ${lit(fixture)})`);
  const p=spawnSync(process.env.SBCL||'sbcl',['--script',join(temp,'runner.lisp')],{encoding:'utf8',maxBuffer:1024*1024});
  process.stdout.write(p.stdout||'');process.stderr.write(p.stderr||'');assert.equal(p.status,0);
 }
}finally{rmSync(temp,{recursive:true,force:true});}
