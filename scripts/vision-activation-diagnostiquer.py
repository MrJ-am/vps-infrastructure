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
CREDENTIALS='d85c11afc1279e0914a8bf7754899065641b5a65'


def projeter_credentials(texte):
    # Catégories fermées uniquement : aucun message, ligne ou valeur du log.
    motifs={
        'permission_refusee':('Permission denied','PermissionError'),
        'fichier_absent':('FileNotFoundError','No such file or directory'),
        'assertion_refusee':('AssertionError',),
        'cle_absente':('KeyError',),
        'credential_non_prive':('Fichier de secret non privé',),
        'smtp_configuration_refusee':('Configuration Proton SMTP invalide',),
        'smtp_tls_refuse':('TLS et vérification du certificat obligatoires',),
        'smtp_format_secret_refuse':('Jeton SMTP invalide',),
        'smtp_adresse_refusee':('Adresse de courrier invalide','Adresse active du jeton requise'),
        'propriete_systemd_refusee':('Unknown assignment','Failed to set unit properties','Invalid property'),
        'creation_unite_refusee':('Failed to start transient service unit','Failed to create bus connection'),
        'utilisateur_dynamique_refuse':('Failed to allocate dynamic user','USER','Failed at step USER'),
        'namespace_refuse':('NAMESPACE','Failed to set up mount namespacing'),
        'chargement_credentials_refuse':('CREDENTIALS','Failed to load credentials','Failed to set up credentials'),
        'python_import_refuse':('ModuleNotFoundError','ImportError'),
        'python_syntaxe_refusee':('SyntaxError','IndentationError'),
    }
    return {nom:any(m in texte for m in valeurs) for nom,valeurs in motifs.items()}


def lignes_python_credentials(texte):
    # Le programme Python passé par -c est public et contient onze lignes.
    # Refuser toute autre source ou ligne ; ne pas exporter le traceback.
    return sorted({int(n) for n in re.findall(r'File "<string>", line ([0-9]{1,2})',texte)
        if 1<=int(n)<=11})


def inspecter_credentials(essai):
    d=Path('/root/vision-essais')/CREDENTIALS
    essai.construction.dossier_prive(d)
    essai.construction.dossier_prive(d/'source')
    essai.construction.dossier_prive(d/'source/scripts')
    essai.construction.dossier_prive(d.parent)
    if any((d/n).exists() for n in ('commence','sql-engage','identite-migree','enregistre','retour-commence')):
        raise ValueError()
    fd=os.open(d,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:texte=essai.prive.lire(fd,'diagnostic-prive.log')
    finally:os.close(fd)
    fichiers={}
    for nom in ('proton-smtp.json','cycle.json','cycle-client.secret','fermeture-hook.secret'):
        p=Path('/var/lib/mrjam-identite')/nom
        try:
            s=p.lstat()
            fichiers[nom]=dict(present=True,regulier=stat.S_ISREG(s.st_mode),
                root=s.st_uid==0,mode=oct(stat.S_IMODE(s.st_mode)),unique=s.st_nlink==1)
        except FileNotFoundError:fichiers[nom]=dict(present=False)
    return dict(essai=CREDENTIALS,avant_armement=True,activation=False,
        categories=projeter_credentials(texte),metadonnees_fichiers=fichiers,
        lignes_programme_python=lignes_python_credentials(texte),
        secrets_lus=False,smtp_contacte=False)


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
        rapport['credentials_preparation']=inspecter_credentials(essai)
        print(json.dumps(rapport),flush=True)
    finally:os.close(essai.fd)


if __name__=='__main__':
    try:main(sys.argv[1])
    except Exception:sys.exit('Diagnostic de l’essai refusé ; aucune donnée privée affichée.')
