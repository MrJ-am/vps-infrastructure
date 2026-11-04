from pathlib import Path
import subprocess,sys,json,hashlib,importlib.util,tomllib,urllib.request,tarfile,io,concurrent.futures
R=Path.cwd();L=R/'.local/ci-artifact-recovery-20261102';G=R/'.local/deployment-20261101/private-histories-20261102/bare';PUB=R/'.local/forgejo-source-history-20261102'
P=R/'operations/builds';spec=importlib.util.spec_from_file_location('prep',P/'prepare.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
def sha(b):return hashlib.sha256(b).hexdigest()
def put(p,b):
 p.parent.mkdir(parents=True,exist_ok=True)
 if p.exists():assert p.read_bytes()==b
 else:p.write_bytes(b);p.chmod(0o644)
def fetch(url):
 with urllib.request.urlopen(url,timeout=45) as r:b=r.read(80*1024*1024+1)
 assert len(b)<=80*1024*1024
 return b
def blob(repo,rev,name):return subprocess.check_output(['git','--git-dir='+str(repo),'show',rev+':'+name],stderr=subprocess.DEVNULL)
# Only exact code selections from the reviewed runtime lock, no full checkout.
lockbytes=(P/'sources-runtime-20261031.lock.json').read_bytes();lock=json.loads(lockbytes);files={}
for key,s in lock['sources'].items():
 repo=G/({'platform':'mrjam-plateforme','vision':'vision','mateval':'matheval'}[key]+'.git')
 for name,h in s['files'].items():
  assert not name.endswith('.gz')
  b=blob(repo,s['commit'],name);assert sha(b)==h
  dest=('mateval-frontend/'+name.removeprefix('frontend/')) if name.startswith('frontend/') else ('platform-source/'+('components/'+key+'/' if key!='platform' else '')+name)
  files[dest]=b
style=json.loads(files['mateval-frontend/style-mrjam.json'])
for name,h in style['fichiers'].items():
 b=blob(PUB/'style-mrjam.git',style['revision'],name);assert sha(b)==h;files['style-source/'+name]=b
elmroot=L/'elm-cache';elmlock=json.loads((L/'validator-code/workflow-runner/elm-cache.lock.json').read_bytes());groups={};mismatches=[]
for name,h in elmlock['files'].items():
 if name=='0.19.1/packages/registry.dat':b=(L/'validator-code/workflow-runner/cache-metadata/elm-registry.dat').read_bytes();assert sha(b)==h;put(elmroot/name,b)
 elif name=='elm-review/2.13.5/0.19.1/versions-cache.json':b=(L/'validator-code/workflow-runner/cache-metadata/elm-review-versions.json').read_bytes();assert sha(b)==h;put(elmroot/name,b)
 else:
  parts=name.split('/');i=parts.index('packages');key=tuple(parts[i+1:i+4]);groups.setdefault(key,[]).append((name,'/'.join(parts[i+4:]),h))
def elmgroup(item):
 (author,project,version),entries=item
 if all((elmroot/name).exists() and sha((elmroot/name).read_bytes())==h for name,path,h in entries):return
 archive=fetch(f'https://codeload.github.com/{author}/{project}/tar.gz/refs/tags/{version}')
 with tarfile.open(fileobj=io.BytesIO(archive),mode='r:gz') as t:
  members={x.name.split('/',1)[1]:x for x in t.getmembers() if '/' in x.name and x.isfile()}
  for name,path,h in entries:
   b=t.extractfile(members[path]).read() if path in members else b''
   if sha(b)!=h:b=fetch(f'https://package.elm-lang.org/packages/{author}/{project}/{version}/{path}')
   if sha(b)!=h:
    mismatches.append({'path':name,'expected':h,'observed':sha(b)});continue
   put(elmroot/name,b)
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:list(ex.map(elmgroup,groups.items()))
(L/'elm-cache-mismatches.json').write_text(json.dumps(mismatches,sort_keys=True,indent=2)+'\n')
print(json.dumps({'elm_cache_packages':len(groups),'elm_cache_files':len(elmlock['files']),'unmatched':len(mismatches)}),flush=True)
baseelm=json.loads((P/'elm-dependencies.lock.json').read_bytes());b=(P/'elm-registry.dat').read_bytes();assert sha(b)==baseelm['registry_sha256'];files['elm-home/0.19.1/packages/registry.dat']=b
for name,s in baseelm['packages'].items():
 for filename,h in s['files'].items():
  rel='0.19.1/packages/'+name+'/'+s['version']+'/'+filename;b=(elmroot/rel).read_bytes();assert sha(b)==h;files['elm-home/'+rel]=b
out=L/'runtime-inputs';out.mkdir(exist_ok=True)
for name,b in files.items():put(out/name,b)
cargo=tomllib.loads(files['platform-source/Cargo.lock'].decode());packages=[p for p in cargo['package'] if p.get('source')];cachedir=R/'.local/mrjam-plateforme-identity/.development/cargo-home/registry/cache/index.crates.io-1949cf8c6b5b557f';downloaded=[]
def cargoone(p):
 name=f"{p['name']}-{p['version']}.crate";cached=cachedir/name
 if cached.is_file():b=cached.read_bytes()
 else:b=fetch(f"https://static.crates.io/crates/{p['name']}/{name}");downloaded.append(name)
 for name,b in m.crate_files(b,p).items():put(out/f"cargo-vendor/{p['name']}-{p['version']}"/name,b)
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:list(ex.map(cargoone,packages))
manifest={'schema_version':1,'scope':'Allowlisted build inputs only, no authority or deployment approval','source_commits':{name:v['commit'] for name,v in lock['sources'].items()},'source_selection_sha256':sha(lockbytes),'elm_dependency_lock_sha256':sha((P/'elm-dependencies.lock.json').read_bytes()),'style_revision':style['revision'],'source_files_sha256':{name:sha(v) for name,v in sorted(files.items())},'cargo_registry_packages':[{'name':p['name'],'version':p['version'],'sha256':p['checksum']} for p in packages],'cargo_vendor_checksum_files_sha256':{str(p.relative_to(out)):sha(p.read_bytes()) for p in sorted((out/'cargo-vendor').glob('*/.cargo-checksum.json'))},'deployment_authorized':False}
b=(json.dumps(manifest,sort_keys=True,indent=2)+'\n').encode();assert sha(b)=='6c4c957933bac12ded038377f3346a800366201a0ae743bce06dd21f87ab50b8';put(out/'materialization.json',b);put(out/'platform-source/materialization.json',b)
print(json.dumps({'source_files':len(files),'cargo_packages':len(packages),'cargo_downloaded':len(downloaded),'materialization_sha256':sha(b)}),flush=True)
