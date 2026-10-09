"""Contrôler l'offre de source construite : licences, code et aucun dossier privé."""
import argparse
import tarfile

p = argparse.ArgumentParser(description=__doc__); p.add_argument('archive'); a = p.parse_args()
with tarfile.open(a.archive) as t:
    noms = {m.name for m in t.getmembers()}
    for m in t.getmembers():
        assert not m.issym() and not m.islnk() and (m.isfile() or m.isdir())
        assert not any(v in m.name for v in ('coordination/', '__pycache__', '.sqlite', '.age', '.pem', '.env', 'proton-smtp.json'))
    for nom in ('./LICENSE', './NOTICE.md', './services/keycloak-mrjam/compiler.sh',
                './services/keycloak-mrjam/src/org/mrjam/identite/CourrielSecurise.java',
                './services/keycloak-mrjam/resources/META-INF/services/org.keycloak.email.EmailSenderProviderFactory',
                './services/mrj-auth/oidc.py', './operations/identite/realm.json'):
        assert nom in noms, 'Source nécessaire manquante : ' + nom
    assert b'GNU AFFERO GENERAL PUBLIC LICENSE' in t.extractfile('./LICENSE').read()
print('Offre de source : licence, extension native, compilation et code présents ; fichiers privés exclus.')
