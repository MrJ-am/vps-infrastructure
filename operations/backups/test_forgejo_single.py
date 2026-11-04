import os,pathlib,re,subprocess,tempfile,hashlib
import sys
script=pathlib.Path(sys.argv[1]).read_text()
with tempfile.TemporaryDirectory(prefix='forgejo-backup-test-') as name:
 root=pathlib.Path(name);(root/'var/lib/forgejo').mkdir(parents=True);(root/'var/backup/forgejo').mkdir(parents=True);(root/'run/lock').mkdir(parents=True)
 source=root/'var/lib/forgejo/example';source.write_text('source one')
 db=root/'db.sql';db.write_text('CREATE TABLE synthetic(id integer);\n')
 def exe(name,body):
  p=root/name;p.write_text('#!/bin/sh\n'+body);p.chmod(0o700);return p
 ctl=exe('systemctl','exit 0\n')
 restore=exe('pg_restore',f'''if [ "$1" = --list ]; then test ! -e "{root}/fail"; else printf '%s\\n' '\\restrict pid-'"$$"; cat "$2"; fi
''')
 env=dict(os.environ)
 path=re.search(r'export PATH="(.*?)"',script).group(1).replace('${PATH:+:}$PATH','');env['PATH']=path
 key=root/'recipient.key';subprocess.run(['age-keygen','-o',str(key)],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True)
 recipient=subprocess.check_output(['age-keygen','-y',str(key)],env=env).decode().strip()
 script=re.sub(r'        recipient=.*', '        recipient='+recipient,script) if '        recipient=' in script else re.sub(r'^recipient=.*','recipient='+recipient,script,flags=re.M)
 script=re.sub(r'/nix/store/[^ /\n]+/bin/systemctl',str(ctl),script)
 script=re.sub(r'/nix/store/[^ /\n]+/bin/pg_restore',str(restore),script)
 script=script.replace('runuser -u forgejo -- pg_dump -h /run/postgresql --format=custom forgejo',f'cat {db}')
 script=script.replace('pg_restore --list',str(restore)+' --list')
 script=script.replace('/var/backup/forgejo',str(root/'var/backup/forgejo')).replace('/run/lock/forgejo-backup.lock',str(root/'run/lock/forgejo-backup.lock')).replace('/var/lib',str(root/'var/lib'))
 program=root/'backup';program.write_text(script);program.chmod(0o700)
 backup=root/'var/backup/forgejo'
 def run(ok=True):
  result=subprocess.run([str(program)],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
  assert (result.returncode==0)==ok,result.stderr.decode()
 def state():return os.readlink(backup/'latest'),hashlib.sha256((backup/'latest/forgejo.tar.age').read_bytes()).hexdigest()
 run();first=state();run();assert state()==first,'unchanged content replaced backup'
 os.utime(source,None);run();assert state()==first,'mtime-only change replaced backup'
 source.write_text('source two');run();second=state();assert second!=first
 assert len(list(backup.glob('.backup-*')))==1
 db.write_text('CREATE TABLE synthetic(id bigint);\n');run();third=state();assert third!=second
 source.write_text('source three');(root/'fail').touch();run(False);assert state()==third
 assert len(list(backup.glob('.backup-*')))==1
 print('PASS: creation, unchanged skip, mtime skip, file change, database change, single copy, failure preserves previous')
