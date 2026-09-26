"""Diagnostic borné d'une publication, sans lire les données applicatives."""
import json,os,re,stat,subprocess,sys
from pathlib import Path
revision=sys.argv[1]
assert os.geteuid()==0 and re.fullmatch('[0-9a-f]{40}',revision)
d=Path('/root/publications-interfaces')/revision
r=json.loads((d/'preparation.json').read_text())
for projet in ('vision','vision-interface','matheval','logique'):
 print(projet, str(Path('/srv/'+projet+'/current').resolve()))
for nom in ('retour.json','termine.json'):
 if (d/nom).is_file():print(nom,(d/nom).read_text())
print('Droits des dépendances préparées :')
for nom in ('server','server/node_modules','server/node_modules/express','server/node_modules/express/package.json'):
 p=Path(r['publications']['matheval'])/nom;s=p.stat();print(nom,oct(stat.S_IMODE(s.st_mode)),s.st_uid,s.st_gid)
print('Journal de la seule unité de publication :')
subprocess.run(['journalctl','--unit=interfaces-appliquer-'+revision[:12]+'.service','--no-pager','--output=cat','--lines=60'],check=True)
print('État des services :')
subprocess.run(['systemctl','is-active','vision','matheval','nginx','mrj-auth','postgresql'],check=True)
subprocess.run(['systemctl','show','vision','vision-migrate','matheval','--property=Id,ActiveState,Result,ExecMainStatus'],check=True)
# Ne sortir que les diagnostics Node, jamais les corps de requête.
p=subprocess.run(['journalctl','--unit=matheval.service','--since=-10min','--no-pager','--output=cat','--lines=150'],check=True,text=True,stdout=subprocess.PIPE)
for l in p.stdout.splitlines():
 if any(k in l for k in ('ERR_MODULE_NOT_FOUND','EACCES','Cannot find package','permission denied','Error [','ERR_MODULE')):print(l)
