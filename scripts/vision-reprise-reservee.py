"""Reprise du seul essai réservé retourné, sans remettre le schéma à zéro."""
import json
import os
from pathlib import Path

ESSAI='d757002ff826431dce2a6401407f55ced5ed2e66'
DIAGNOSTIC='f729c5a2b9ffe46a06a022e0cb481a9f4134817b'


def exiger(v):
    if not v:raise ValueError('Reprise réservée refusée')


def verifier_diagnostic(r):
    exiger(type(r.get('version')) is int and r['version']==1 and
        r.get('infrastructure')==DIAGNOSTIC and r.get('essai')==ESSAI and
        r.get('schema')==dict(nombre=25,maximum=25))
    exiger(all(r.get(k) is True for k in ('retour_effectif','socle_ancien_et_compte_verifies',
        'identite_commune_presente','association_initiale_preservee','sql_engage',
        'identite_migree','identite_courante_retablie')) and
        r.get('activation') is False and r.get('inscriptions') is False)


def verifier_precedent(root,prive,construction):
    verifier_diagnostic(json.loads((root/'operations/vision-activation-diagnostic-reel.json').read_text()))
    d=Path('/root/vision-essais')/ESSAI
    construction.dossier_prive(d)
    fd=os.open(d,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        for n in ('commence','sql-engage','identite-migree','identite-retablie','retour-termine','echec'):
            exiger(prive.lire(fd,n)=='1\n')
        exiger(not (d/'enregistre').exists())
        plan=json.loads(prive.lire(fd,'plan.json'))
        exiger(plan['infrastructure']==ESSAI and Path('/run/current-system').resolve()==Path(plan['ancien']) and
            Path('/nix/var/nix/profiles/system').resolve()==Path(plan['ancien']))
    finally:os.close(fd)


def verifier_association(sql,identite,historique):
    # Une association existante exacte est constatée ; jamais remplacée,
    # ni déduite du seul courriel ni réinsérée après retour.
    obtenu=json.loads(sql("SELECT json_build_object('comptes',(SELECT count(*) FROM vision_gestion.comptes),'administrateurs',(SELECT count(*) FROM vision_gestion.comptes WHERE administrateur),'identites',(SELECT count(*) FROM vision_gestion.identites),'issuer',i.emetteur,'sujet',i.sujet,'utilisateur',i.utilisateur,'actif',c.actif,'inscriptions',(SELECT inscriptions_ouvertes FROM vision_gestion.configuration)) FROM vision_gestion.identites i JOIN vision_gestion.comptes c USING(utilisateur);"))
    attendu=dict(comptes=1,administrateurs=1,identites=1,issuer=identite['issuer'],
        sujet=identite['sujet'],utilisateur=historique['utilisateur_historique'],actif=True,inscriptions=False)
    exiger(obtenu==attendu)
    exiger(sql("SELECT NOT EXISTS(SELECT FROM vision_gestion.effacements) AND NOT EXISTS(SELECT FROM vision_gestion.admissions WHERE annulee_a IS NULL AND consommee_a IS NULL AND expire_a>now());")=='t')
    exiger(sql('SELECT count(*)=25 AND max(version)=25 FROM vision_schema_migrations;')=='t')


def roles_fixture():
    # Ces rôles sont nécessaires à pg_restore d'un dump déjà migré ; cette
    # commande est exclusivement exécutée dans le nouveau cluster isolé.
    roles=('vision_migration','vision_administration','vision_identite','vision_cycle','vision_admission','vision_fermeture')
    return '\n'.join('CREATE ROLE '+r+' '+('NOLOGIN' if r=='vision_migration' else 'LOGIN')+
        ' NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;' for r in roles)
