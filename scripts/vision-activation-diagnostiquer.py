"""Lire le seul essai d757 terminé, sans SQL de mutation ni journal brut."""
import grp
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import sys

ROOT=Path(__file__).resolve().parents[1]
ESSAI='d757002ff826431dce2a6401407f55ced5ed2e66'


def main(revision):
    if os.geteuid()!=0 or not re.fullmatch('[a-f0-9]{40}',revision):raise ValueError()
    if ROOT!=Path('/root/vision-activation-diagnostics')/revision/'source':raise ValueError()
    source=Path('/root/vision-essais')/ESSAI/'source'
    spec=importlib.util.spec_from_file_location('essai_diagnostic',source/'scripts/vision-essai-activer.py')
    e=importlib.util.module_from_spec(spec);spec.loader.exec_module(e)
    essai=e.Essai(ESSAI)
    try:
        e.exiger((essai.d/'retour-termine').is_file() and not (essai.d/'enregistre').exists())
        essai.verifier_socle()
        e.exiger(hashlib.sha256((source/'scripts/vision-essai-retour.sh').read_bytes()).digest()==
            hashlib.sha256((ROOT/'scripts/vision-essai-retour.sh').read_bytes()).digest())
        repertoire=Path('/srv/vision-essais');info=repertoire.lstat()
        e.exiger(stat.S_ISDIR(info.st_mode) and info.st_uid==0 and not info.st_mode&0o022)
        schema=json.loads(essai.sql('vision',"SELECT json_build_object('nombre',count(*),'maximum',max(version)) FROM vision_schema_migrations;"))
        e.exiger(type(schema['nombre']) is int and type(schema['maximum']) is int and
            schema['nombre']==schema['maximum'] and 18<=schema['maximum']<=25)
        identite=essai.sql('postgres',"SELECT EXISTS(SELECT FROM pg_database WHERE datname='mrjam_identite');")=='t'
        compte=False
        if schema['maximum']==25:
            attendu=essai.lire('association-privee.json');i=attendu['identite'];h=attendu['historique']
            q="SELECT count(*)=1 AND bool_and(emetteur="+essai.acl.litteral(i['issuer'])+" AND sujet="+essai.acl.litteral(i['sujet'])+" AND utilisateur="+essai.acl.litteral(h['utilisateur_historique'])+") FROM vision_gestion.identites;"
            compte=essai.sql('vision',q)=='t' and essai.sql('vision',"SELECT count(*)=1 AND bool_and(actif AND administrateur) FROM vision_gestion.comptes;")=='t'
            e.exiger(essai.sql('vision',"SELECT NOT inscriptions_ouvertes FROM vision_gestion.configuration;")=='t')
        diagnostic=''
        if (essai.d/'diagnostic-prive.log').exists():diagnostic=essai.prive.lire(essai.fd,'diagnostic-prive.log')
        noms=('vision.service','vision-migrate.service','keycloak.service','mrj-auth.service',
            'vision-gestion.service','vision-cycle.service','mrjam-admission.service','mrjam-fermeture.service','mrjam-courriel.service')
        echecs=[n for n in noms if n in diagnostic and
            any(n in ligne and any(v in ligne.lower() for v in ('failed','failure','échec','chdir','permission denied')) for ligne in diagnostic.splitlines())]
        rapport=dict(version=1,infrastructure=revision,essai=ESSAI,retour_effectif=True,
            socle_ancien_et_compte_verifies=True,schema=schema,
            identite_commune_presente=identite,association_initiale_preservee=compte,
            sql_engage=(essai.d/'sql-engage').is_file(),identite_migree=(essai.d/'identite-migree').is_file(),
            identite_courante_retablie=(essai.d/'identite-retablie').is_file(),
            parent_backend_mode=oct(stat.S_IMODE(info.st_mode)),
            parent_backend_traversable_par_vision=info.st_gid==grp.getgrnam('vision').gr_gid and bool(info.st_mode&0o010),
            changement_repertoire_refuse='CHDIR' in diagnostic or 'Permission denied' in diagnostic,
            services_en_echec_dans_diagnostic=echecs,activation=False,inscriptions=False,
            donnees_production_modifiees=False)
        print(json.dumps(rapport),flush=True)
    finally:os.close(essai.fd)


if __name__=='__main__':
    try:main(sys.argv[1])
    except Exception:sys.exit('Diagnostic de l’essai refusé ; aucune donnée privée affichée.')
