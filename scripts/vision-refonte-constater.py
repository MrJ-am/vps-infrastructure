#!/usr/bin/env python3
"""Constater après finalisation, en lecture seule, l'état réellement actif."""
import importlib.util,json,os,re,subprocess,sys
from pathlib import Path
revision,application=sys.argv[1:]
assert os.geteuid()==0 and all(re.fullmatch('[0-9a-f]{40}',v) for v in (revision,application))
d=Path('/root/vision-refonte-operations')/revision
assert (d/'enregistre').is_file() and not (d/'retour-engage').exists()
termine=json.loads((d/'termine.json').read_text())
assert termine['revision']==revision and termine['application']==application
spec=importlib.util.spec_from_file_location('publication',d/'source/scripts/vision-refonte-deployer.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
assert m.etat()==termine['etat']
m.services()
assert m.psql('vision','SELECT vision_revision_contrat()').strip()==b'6'
assert m.psql('vision','SELECT count(*) FROM vision_schema_migrations WHERE version=15').strip()==b'1'
for suffixe in ('retour-'+revision[:12]+'.timer','appliquer-'+revision[:12]+'.service'):
    assert subprocess.run(['systemctl','is-active','--quiet','vision-refonte-'+suffixe]).returncode!=0
assert Path('/srv/vision/current/revision-application.txt').read_text().strip()==application
manifeste=json.loads(Path('/srv/vision-interface/current/manifest.json').read_text())
assert manifeste['revisionApplication']==application
for nom,attendu in manifeste['fichiers'].items():
    assert m.empreinte(Path('/srv/vision-interface/current')/nom)==attendu
print(json.dumps({'controle_apres_finalisation':True,'retour_inactif':True,'etat':m.etat(),'application':application,'rapport_migration':termine['rapport']},ensure_ascii=False,indent=2))
