"""Retour ACL, owners et RLS sur le socle 18 puis 25, sans perte de contenu.

Exclusivement dans le cluster synthétique loopback de la qualification.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import uuid
import psycopg
from psycopg import sql

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('acl', ROOT / 'scripts/vision-acl.py')
module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)


def verifier(vision):
    assert os.environ['PGHOST'] == '127.0.0.1' and os.environ['PGUSER'] == 'postgres'
    base = 'vision_acl_qualification_' + uuid.uuid4().hex[:12]
    dsn = dict(host=os.environ['PGHOST'], port=os.environ.get('PGPORT', '5432'),
        user='postgres', password=os.environ['PGPASSWORD'])
    with psycopg.connect(**dsn, dbname='postgres', autocommit=True) as root:
        root.execute(sql.SQL('CREATE DATABASE {} OWNER vision').format(sql.Identifier(base)))
        try:
            with psycopg.connect(**dsn, dbname=base, autocommit=True) as db:
                db.execute('CREATE EXTENSION vector')
                db.execute('SET ROLE vision')
                for p in sorted((vision / 'migrations').glob('*.sql')):
                    if int(p.name.split('_', 1)[0]) <= 18: db.execute(p.read_text())
                db.execute("INSERT INTO vision_profils(utilisateur) VALUES('qualification-owner')")
                db.execute("INSERT INTO vision_fiches(utilisateur,titre,contenu) VALUES('qualification-owner','Privé synthétique','À conserver')")
                db.execute('RESET ROLE')
                def requete(q):
                    return json.dumps(db.execute(q).fetchone()[0], default=str)
                avant = module.relever(requete)
                lignes = db.execute('SELECT to_jsonb(t) FROM vision_fiches t ORDER BY id').fetchall()
                db.execute('SET ROLE vision')
                for p in sorted((vision / 'migrations').glob('*.sql')):
                    if int(p.name.split('_', 1)[0]) >= 19: db.execute(p.read_text())
                db.execute('RESET ROLE')
                db.execute((vision / 'scripts/roles.sql').read_text())
                retour = module.retour(avant)
                # Une admission nouvelle doit interdire toute réouverture de
                # l'ancien binaire, avant le moindre retour de privilège.
                db.execute("INSERT INTO vision_gestion.comptes(utilisateur,affichage) VALUES('qualification-tiers','Synthétique')")
                try:
                    db.execute(retour)
                    raise AssertionError('Retour ancien accepté après admission d’un tiers')
                except psycopg.errors.RaiseException:
                    db.execute('ROLLBACK')
                db.execute("DELETE FROM vision_gestion.comptes WHERE utilisateur='qualification-tiers'")
                db.execute(retour); db.execute(retour)
                apres = module.relever(requete)
                historiques = {(o['type'], o['nom']) for o in avant['objets']}
                assert [o for o in apres['objets'] if (o['type'], o['nom']) in historiques] == avant['objets']
                assert apres['role'] == avant['role']
                assert db.execute('SELECT to_jsonb(t) FROM vision_fiches t ORDER BY id').fetchall() == lignes
            print(json.dumps(dict(retour_acl_owners_rls=True, retour_rejouable=True,
                refus_apres_nouvelle_admission=True, contenus_preserves=True, restauration_production=False)))
        finally:
            root.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(base)))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--vision', type=Path, required=True)
    a = p.parse_args(); verifier(a.vision.resolve())
