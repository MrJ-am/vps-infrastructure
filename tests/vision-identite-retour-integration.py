"""Transfert inverse courant et restauration atomique dans deux bases jetables."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import uuid


def verifier(conteneur):
    assert re.fullmatch(r'[A-Za-z0-9_.-]{1,80}',conteneur)
    suffixe=uuid.uuid4().hex[:12]
    nouveau='retour_identite_nouveau_'+suffixe
    ancien='retour_identite_ancien_'+suffixe
    role='retour_identite_'+suffixe
    def commande(*args,entree=None,ok=True):
        r=subprocess.run(['docker','--host=unix:///var/run/docker.sock','exec','-i',conteneur,*args],
            input=entree,capture_output=True,timeout=90)
        assert (r.returncode==0)==ok, 'Commande synthétique de récupération refusée'
        return r.stdout
    def sql(base,q,ok=True):
        return commande('psql','-XAtq','-v','ON_ERROR_STOP=1','-U','postgres','-d',base,
            '-f','-',entree=q.encode(),ok=ok).decode().strip()
    sql('postgres',f'CREATE ROLE {role} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT;')
    crees=[]
    try:
        for base in (nouveau,ancien):
            sql('postgres',f'CREATE DATABASE {base} OWNER {role};');crees.append(base)
            sql(base,f'''SET ROLE {role};
                CREATE TABLE realm(id text PRIMARY KEY);
                CREATE TABLE user_entity(id text PRIMARY KEY,realm text REFERENCES realm(id));
                CREATE TABLE credential(id text PRIMARY KEY,user_id text REFERENCES user_entity(id),valeur text);
                INSERT INTO realm VALUES ('realm-initial');
                INSERT INTO user_entity VALUES ('sujet-stable','realm-initial');
                INSERT INTO credential VALUES ('pwd','sujet-stable','empreinte-initiale'),('otp','sujet-stable','otp-initial');''')
        # Des modifications légitimes ont lieu après le transfert initial.
        sql(nouveau,"UPDATE credential SET valeur=CASE id WHEN 'pwd' THEN 'empreinte-courante' ELSE 'otp-courant' END;")
        avant=sql(ancien,'SELECT json_agg(t ORDER BY id) FROM credential t;')
        # Archive partielle : son FK post-data échoue après remplacement des tables.
        # L'ancien realm n'a pas la nouvelle référence ; toute la restauration
        # doit être annulée, y compris les données déjà rechargées.
        sql(nouveau,"INSERT INTO realm VALUES ('realm-nouveau'); UPDATE user_entity SET realm='realm-nouveau';")
        incomplet=commande('pg_dump','-Fc','-U','postgres','-d',nouveau,'-t','user_entity','-t','credential')
        options=('pg_restore','--single-transaction','--exit-on-error','--clean','--if-exists',
            '--no-owner','--no-privileges','--role='+role,'-U','postgres')
        commande(*options,'-d',ancien,entree=incomplet,ok=False)
        assert sql(ancien,'SELECT json_agg(t ORDER BY id) FROM credential t;')==avant
        assert sql(ancien,"SELECT realm FROM user_entity WHERE id='sujet-stable';")=='realm-initial'
        courant=commande('pg_dump','-Fc','-U','postgres','-d',nouveau)
        for _ in range(2):
            commande(*options,'-d',ancien,entree=courant)
            for table in ('realm','user_entity','credential'):
                q=f'SELECT json_agg(t ORDER BY id) FROM {table} t;'
                assert sql(ancien,q)==sql(nouveau,q)
        # Après la marque d'inversion, l'ancien cluster est la référence.
        # Son contenu ne peut plus être écrasé par un rejeu de l'ancien transfert.
        sql(ancien,"UPDATE credential SET valeur='mise-a-jour-apres-retour' WHERE id='pwd';")
        assert sql(ancien,"SELECT valeur FROM credential WHERE id='pwd';")=='mise-a-jour-apres-retour'
        print(json.dumps(dict(donnees_synthetiques=True,identite_courante_conservee=True,
            sujet_mot_de_passe_otp_conserves=True,retour_transactionnel_partiel_refuse=True,
            retour_rejoue_deux_fois=True,ancienne_copie_non_utilisee=True)))
    finally:
        for base in reversed(crees):sql('postgres','DROP DATABASE '+base+';')
        sql('postgres','DROP ROLE '+role+';')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--conteneur',required=True);a=p.parse_args()
    verifier(a.conteneur)
