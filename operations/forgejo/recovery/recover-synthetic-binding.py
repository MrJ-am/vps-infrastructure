from pathlib import Path
import subprocess,hashlib,json,os,shutil
R=Path.cwd();L=R/'.local/ci-artifact-recovery-20261102';G=R/'.local/deployment-20261101/private-histories-20261102/bare/mrjam-validation.git';new=L/'rules-fixture.git'
E={'PATH':os.environ['PATH'],'LANG':'C','LC_ALL':'C','GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':'/dev/null','GIT_TERMINAL_PROMPT':'0','GIT_NO_REPLACE_OBJECTS':'1','GIT_AUTHOR_NAME':'Synthetic qualification','GIT_AUTHOR_EMAIL':'fixture@example.invalid','GIT_COMMITTER_NAME':'Synthetic qualification','GIT_COMMITTER_EMAIL':'fixture@example.invalid','GIT_AUTHOR_DATE':'2026-10-31T00:00:00Z','GIT_COMMITTER_DATE':'2026-10-31T00:00:00Z','GIT_ALTERNATE_OBJECT_DIRECTORIES':str(G/'objects')}
def git(*args,data=None):return subprocess.check_output(['git','-c','core.hooksPath=/dev/null',*args],env=E,input=data,stderr=subprocess.DEVNULL)
git('init','--bare',str(new));prefix=('--git-dir='+str(new),)
git(*prefix,'read-tree','eb71ffe5944943474c5ee483e66c270b5976ab90')
workflow=(R/'operations/forgejo/independent-validation.yml').read_bytes();blob=git(*prefix,'hash-object','-w','--stdin',data=workflow).decode().strip()
git(*prefix,'update-index','--add','--cacheinfo','100644,'+blob+',.forgejo/workflows/independent-validation.yml')
tree=git(*prefix,'write-tree').decode().strip();revision=git(*prefix,'commit-tree',tree,data=b'Offline synthetic workflow integration; validation bytes from eb71ffe5944943474c5ee483e66c270b5976ab90\n').decode().strip()
assert tree=='f2c84117b2ae7e0f0c3bf34ab82d47dd957ef90b' and revision=='93bd67666a3b4be9657c333931fa25b2359e165b'
# No branch or governance ref is created; this commit is only a historical fixture.
shutil.copytree(L/'proposal-base',L/'proposal-fixture')
p=L/'proposal-fixture/manifest.json';v=json.loads(p.read_text());v['rules_revision']=revision;p.write_text(json.dumps(v,sort_keys=True,separators=(',',':'))+'\n');assert hashlib.sha256(p.read_bytes()).hexdigest()=='5857e70c38d41bb739b460a131d5eef6696985eb247ba9c9420a7605e51e5087'
p=L/'policy-fixture.json';v=json.loads((L/'policy-base.json').read_text());v['rules_revision']=revision;p.write_text(json.dumps(v,sort_keys=True,indent=2)+'\n');assert hashlib.sha256(p.read_bytes()).hexdigest()=='5a44dde8bd4c6e36eddb41f11250d3b8c0b07093ce46d646880cc2652f96cf91'
print(json.dumps({'fixture_tree':tree,'fixture_revision':revision,'proposal_sha256':'5857e70c38d41bb739b460a131d5eef6696985eb247ba9c9420a7605e51e5087','policy_sha256':'5a44dde8bd4c6e36eddb41f11250d3b8c0b07093ce46d646880cc2652f96cf91','governance_references_modified':False,'old_private_blobs_read':False}))
