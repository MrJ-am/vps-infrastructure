"""Restaurer les textes multioctets avec le véritable démarrage du préparateur.

Deux clusters privés dans le seul conteneur synthétique PostgreSQL 17 :
reproduire le refus SQL_ASCII puis vérifier UTF-8, migrations et retour des ACL.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import re
import subprocess
from unittest.mock import patch
import uuid

ROOT = Path(__file__).resolve().parents[1]


def importer(nom, chemin):
    spec = importlib.util.spec_from_file_location(nom, chemin)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def verifier(conteneur, vision):
    assert re.fullmatch(r'[A-Za-z0-9_-]{1,80}', conteneur)
    image = subprocess.check_output(['docker', 'inspect', '--format', '{{.Config.Image}}', conteneur], text=True).strip()
    assert image == 'pgvector/pgvector:0.8.0-pg17', 'Conteneur de qualification requis'
    m = importer('preparer_utf8', ROOT / 'scripts/vision-multiutilisateur-preparer.py')
    audit = importer('audit_utf8', ROOT / 'scripts/vision-restauration-auditer.py')
    nom = 'vision_encodage_' + uuid.uuid4().hex[:12]
    b = Path('/usr/lib/postgresql/17/bin')

    def executer(*args, entree=None, exiger=True):
        r = subprocess.run(['docker', 'exec', '-i', '-u', 'postgres', conteneur, *map(str, args)],
            input=entree, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if exiger and r.returncode: raise RuntimeError('Commande synthétique refusée : ' + Path(str(args[0])).name)
        return r

    def commande(*args, entree=None, env=None):
        assert args[:4] == ('runuser', '-u', 'postgres', '--')
        return executer(*args[4:], entree=entree).stdout

    def sql(base, texte, socket='/var/run/postgresql'):
        return executer('psql', '-XAtq', '-v', 'ON_ERROR_STOP=1', '-h', socket, '-U', 'postgres',
            '-d', base, '-f', '-', entree=("SET TIME ZONE 'UTC'; SET DateStyle='ISO';\n" + texte).encode()).stdout.decode().strip()

    sql('postgres', 'CREATE DATABASE ' + nom + ' OWNER vision;')
    try:
        migrations = sorted((vision / 'migrations').glob('*.sql'))
        sql(nom, 'CREATE EXTENSION vector; SET ROLE vision;' + ''.join(p.read_text() for p in migrations if int(p.name.split('_')[0]) <= 18) +
            "INSERT INTO vision_profils(utilisateur) VALUES('qualification');"
            "INSERT INTO vision_fiches(utilisateur,titre,contenu) VALUES('qualification',repeat('é',180),'Été, 漢字, € et 😀');"
            "INSERT INTO vision_items(utilisateur,titre,contenu,objectifs,sens) VALUES('qualification',repeat('é',180),'Été, 漢字, € et 😀',ARRAY['Retenir'],ARRAY['Sens synthétique']);")
        tables = json.loads(sql(nom, "SELECT json_agg(tablename ORDER BY tablename) FROM pg_tables WHERE schemaname='public' AND tablename LIKE 'vision_%' AND tablename<>'vision_schema_migrations';"))
        releve = m.acl.relever(lambda q: sql(nom, q))
        with patch.object(m, 'commande', commande):
            empreintes = m.empreintes('/var/run/postgresql', nom, tables)
        dump = executer('pg_dump', '-Fc', '-U', 'postgres', nom).stdout
        for utf8 in (False, True):
            dossier = Path('/tmp') / (nom + ('-utf8' if utf8 else '-ascii'))
            executer('mkdir', '-m', '700', dossier)
            actif = False
            try:
                if utf8:
                    with patch.object(m, 'commande', commande): m.initialiser_cluster(dossier, b)
                else:
                    executer(b / 'initdb', '-D', dossier / 'data', '--auth-local=trust', '--auth-host=reject', '--no-locale')
                    executer(b / 'pg_ctl', '-D', dossier / 'data', '-l', dossier / 'serveur.log', '-w',
                        '-o', "-c listen_addresses='' -c unix_socket_directories=" + str(dossier), 'start')
                actif = True
                assert sql('postgres', "SHOW listen_addresses;", str(dossier)) == ''
                assert sql('postgres', "SHOW server_encoding;", str(dossier)) == ('UTF8' if utf8 else 'SQL_ASCII')
                sql('postgres', 'CREATE ROLE vision LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS; CREATE DATABASE ' + nom + ' OWNER vision;', str(dossier))
                r = executer(b / 'pg_restore', '--exit-on-error', '-h', dossier, '-U', 'postgres', '-d', nom, entree=dump, exiger=False)
                if not utf8:
                    assert r.returncode != 0
                    assert audit.classer(r.stderr.decode(errors='replace'))['longueur_titre_fiche_refusee']
                    continue
                assert r.returncode == 0, 'Restauration UTF-8 refusée'
                assert sql(nom, "SELECT char_length(titre)=180 AND contenu='Été, 漢字, € et 😀' FROM vision_fiches;", str(dossier)) == 't'
                with patch.object(m, 'commande', commande):
                    assert m.empreintes(str(dossier), nom, tables) == empreintes
                    for p in migrations:
                        if int(p.name.split('_')[0]) >= 19: m.sql(str(dossier), nom, p.read_text())
                    m.sql(str(dossier), nom, (vision / 'scripts/roles.sql').read_text())
                    assert m.empreintes(str(dossier), nom, tables) == empreintes
                    retour = m.acl.retour(releve)
                    m.sql(str(dossier), nom, retour); m.sql(str(dossier), nom, retour)
                    apres = m.acl.relever(lambda q: m.sql(str(dossier), nom, q))
                    historiques = {(o['type'], o['nom']) for o in releve['objets']}
                    assert [o for o in apres['objets'] if (o['type'], o['nom']) in historiques] == releve['objets']
                    assert apres['role'] == releve['role']
                    assert m.empreintes(str(dossier), nom, tables) == empreintes
            finally:
                if actif: executer(b / 'pg_ctl', '-D', dossier / 'data', '-m', 'fast', '-w', 'stop')
                executer('rm', '-rf', dossier)
        print(json.dumps(dict(refus_ascii_reproduit=True, restauration_utf8=True,
            textes_multioctets_preserves=True, migrations_sans_perte=True,
            retour_acl_rejoue_deux_fois=True, postgres_tcp=False, production=False)))
    finally:
        sql('postgres', 'DROP DATABASE ' + nom + ' WITH (FORCE);')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--conteneur', required=True); p.add_argument('--vision', type=Path, required=True)
    a = p.parse_args(); verifier(a.conteneur, a.vision.resolve())
