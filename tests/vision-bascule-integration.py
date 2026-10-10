"""Association explicite et retour dans une base synthétique jetable."""
import argparse
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import uuid

ROOT = Path(__file__).resolve().parents[1]


def charger(nom):
    s = importlib.util.spec_from_file_location(nom, ROOT/'scripts'/(nom+'.py'))
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


def verifier(conteneur, vision):
    assert re.fullmatch(r'[A-Za-z0-9_.-]{1,80}', conteneur)
    base = 'vision_bascule_qualification_'+uuid.uuid4().hex[:12]
    acl = charger('vision-acl'); association = charger('vision-bascule-principaux')
    def sql(q, db=base, ok=True):
        r = subprocess.run(['docker','--host=unix:///var/run/docker.sock','exec','-i',conteneur,
            'psql','-XAtq','-v','ON_ERROR_STOP=1','-U','postgres','-d',db,'-f','-'],
            input=("SET TIME ZONE 'UTC'; SET DateStyle='ISO';\n"+q).encode(),capture_output=True,timeout=120)
        assert (r.returncode == 0) == ok, 'SQL synthétique refusé'
        return r.stdout.decode().strip()
    sql('CREATE DATABASE '+base+' OWNER vision;', db='postgres')
    try:
        sql('CREATE EXTENSION vector;')
        migrations = sorted((vision/'migrations').glob('*.sql'))
        sql('SET ROLE vision;\n'+'\n'.join(p.read_text() for p in migrations if int(p.name.split('_',1)[0])<=18))
        sql("SET ROLE vision; INSERT INTO vision_profils(utilisateur) VALUES('owner-synthetique'); INSERT INTO vision_fiches(utilisateur,titre,contenu) VALUES('owner-synthetique','Synthétique','À conserver');")
        avant = acl.relever(sql)
        donnees = sql('SELECT to_jsonb(t) FROM vision_fiches t ORDER BY id;')
        sql('\n'.join(p.read_text() for p in migrations if int(p.name.split('_',1)[0])==19))
        # Échec possible avant admissions et avant roles.sql : le retour reste valide.
        sql(acl.retour(avant))
        assert sql('SELECT to_jsonb(t) FROM vision_fiches t ORDER BY id;') == donnees
        sql('\n'.join(p.read_text() for p in migrations if int(p.name.split('_',1)[0])>=20))
        sql((vision/'scripts/roles.sql').read_text())
        identite = dict(issuer=association.ISSUER,sujet='11111111-1111-4111-8111-111111111111')
        historique = dict(utilisateur_historique='owner-synthetique',proprietaires=1,authentification_unique=True)
        q = association.association_sql(identite,historique,acl.litteral)
        sql(q)
        assert sql("SELECT count(*)=1 AND bool_and(administrateur) FROM vision_gestion.comptes;") == 't'
        assert sql("SELECT count(*)=1 AND bool_and(sujet='11111111-1111-4111-8111-111111111111' AND utilisateur='owner-synthetique') FROM vision_gestion.identites;") == 't'
        assert sql("SELECT count(*)=0 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relname LIKE 'vision_%' AND c.relkind IN ('r','p','v','m') AND has_table_privilege('vision_administration',c.oid,'SELECT,INSERT,UPDATE,DELETE');") == 't'
        sql(q,ok=False)
        assert sql('SELECT to_jsonb(t) FROM vision_fiches t ORDER BY id;') == donnees
        # La copie initiale ne doit pas écraser une donnée ajoutée après migration.
        sql("UPDATE vision_fiches SET titre='Modifié pendant essai' WHERE utilisateur='owner-synthetique';")
        donnees=sql('SELECT to_jsonb(t) FROM vision_fiches t ORDER BY id;')
        retour = acl.retour(avant)
        sql("INSERT INTO vision_gestion.comptes(utilisateur,affichage) VALUES('tiers-synthetique','Synthétique');")
        sql(retour,ok=False)
        sql("DELETE FROM vision_gestion.comptes WHERE utilisateur='tiers-synthetique';")
        sql("UPDATE vision_gestion.comptes SET actif=false WHERE utilisateur='owner-synthetique';")
        sql(retour,ok=False)
        sql("UPDATE vision_gestion.comptes SET actif=true WHERE utilisateur='owner-synthetique'; INSERT INTO vision_gestion.effacements(utilisateur,purger_apres) VALUES('owner-synthetique',now()+interval '30 days');")
        sql(retour,ok=False)
        sql("DELETE FROM vision_gestion.effacements;")
        for _ in range(2):
            sql(retour)
            apres = acl.relever(sql); objets = {(o['type'],o['nom']) for o in avant['objets']}
            assert [o for o in apres['objets'] if (o['type'],o['nom']) in objets] == avant['objets']
            assert apres['role'] == avant['role']
            assert sql('SELECT to_jsonb(t) FROM vision_fiches t ORDER BY id;') == donnees
        # Refuser une réactivation du propriétaire après sa suppression.
        sql('DELETE FROM vision_gestion.identites; DELETE FROM vision_gestion.comptes;')
        sql(retour,ok=False)
        print(json.dumps(dict(donnees_synthetiques=True,association_expresse=True,administrateur_applicatif_unique=True,
            admin_sans_contenu=True,rejeu_association_refuse=True,retour_avec_tiers_refuse=True,
            retour_partiel_sans_admissions=True,retour_apres_effacement_refuse=True,
            retour_rejoue_deux_fois=True,donnees_ajoutees_pendant_essai_conservees=True,donnees_conservees=True)))
    finally: sql('DROP DATABASE '+base+';',db='postgres')


if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('--conteneur',required=True);p.add_argument('--vision',type=Path,required=True);a=p.parse_args()
    verifier(a.conteneur,a.vision)
