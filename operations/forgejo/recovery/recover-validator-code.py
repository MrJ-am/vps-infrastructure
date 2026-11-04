from pathlib import Path
import subprocess,json,hashlib,os
R=Path.cwd();L=R/'.local/ci-artifact-recovery-20261102';V=L/'validator-code';G=R/'.local/deployment-20261101/private-histories-20261102/bare/mrjam-validation.git';REV='eb71ffe5944943474c5ee483e66c270b5976ab90'
fixed=['rules-provenance.json','check_git_tree.py','test_http_boundary.py','fixtures/vision-outils-source.json','review/elm.json','review/ressources.json','review/src/ReviewConfig.elm','review/src/MrJam/Presentation.elm','review/tests/PresentationTest.elm']
fixed += ['workflow-runner/'+p for p in ['package.nix','qualification-package.nix','elm-cache.nix','elm-cache.lock.json','verify_cache.py','cache-metadata/elm-registry.dat','cache-metadata/elm-review-versions.json','npm-tools.nix','npm_materialize.py','npm-tools.lock.json','npm-resources.nix','npm-resources.lock.json','frontend-support.nix','prepare_resources.py','policy.py','sandbox.py','pg_stage.py','server_wrapper.py','cpu-limit.cjs','frontend_assembly.py','logo_exports.cjs','runner.py','qualify_frontends.py']]
entries=subprocess.check_output(['git','--git-dir='+str(G),'ls-tree','-r','-z',REV]).split(b'\0')
records={}
for entry in entries:
 if not entry:continue
 meta,name=entry.split(b'\t',1);name=name.decode();mode,kind,oid=meta.decode().split()
 if name not in fixed and not name.startswith('frontend-qualification/overrides/'):continue
 assert kind=='blob' and mode in ['100644','100755']
 raw=subprocess.check_output(['git','--git-dir='+str(G),'cat-file','blob',oid]);p=V/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw);p.chmod(int(mode,8)&0o777)
 records[name]={'blob':oid,'sha256':hashlib.sha256(raw).hexdigest(),'mode':mode}
assert set(fixed)<=set(records)
(L/'validator-code-selection.json').write_text(json.dumps(records,sort_keys=True,indent=2)+'\n')
print(json.dumps({'selected_code_files':len(records)}))
