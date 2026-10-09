"""Garde-fou fermé, preuves liées et imports sans lancement de serveur."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def charger(nom, fichier):
    spec = importlib.util.spec_from_file_location(nom, ROOT / 'scripts' / fichier)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


v = charger('verification_composants', 'vision-mrjam-verifier.py')
m = charger('construction_composants', 'vision-mrjam-composants-construire.py')


class Composants(unittest.TestCase):
    def setUp(self):
        self.resume = dict(version=1, keycloak_version='26.7.3', jdbc_unix=True,
            garde_activation=True, generation_constructible=False, preconditions_validees=False,
            inscriptions=False, postgres_tcp=False, activation=False, fournisseur_epingle=True,
            fournisseur_source='/nix/store/' + 'g' * 32 + '-fournisseur',
            lot='/nix/store/' + 'a' * 32 + '-lot', keycloak='/nix/store/' + 'b' * 32 + '-keycloak',
            sources='/nix/store/' + 'c' * 32 + '-sources', unites={})
        for nom, utilisateur in v.UTILISATEURS.items():
            self.resume['unites'][nom] = dict(utilisateur=utilisateur,
                chemin='/nix/store/' + 'd' * 32 + '-unit',
                executable='/nix/store/' + 'e' * 32 + '-python/bin/python3 /nix/store/' + 'f' * 32 + '-source/server.py')
        self.preuve = json.loads((ROOT / 'operations/vision-identite-import-qualification.json').read_text())
        self.rapport = {k: val for k, val in self.preuve.items() if k not in
            ('run', 'job', 'socle_inchange', 'services_actifs', 'sondes_http_tls', 'nouvelle_connexion_ssh')}
        self.candidat = json.loads((ROOT / 'operations/vision-multiutilisateur-candidat.json').read_text())
        self.unix = json.loads((ROOT / 'operations/vision-identite-unix-qualification.json').read_text())
        self.build = json.loads((ROOT / 'operations/vision-identite-construction.json').read_text())

    def test_garde_ferme_et_preuve_import_coherente(self):
        v.verifier_resume(self.resume)
        m.preuve_import(self.rapport, self.preuve, self.candidat, self.unix, self.build)

    def test_activation_tcp_generation_ou_chemin_externe_refuses(self):
        for cle in ('generation_constructible', 'preconditions_validees', 'inscriptions', 'postgres_tcp', 'activation'):
            with self.subTest(cle=cle), self.assertRaises(ValueError):
                v.verifier_resume({**self.resume, cle: True})
        for cle in ('garde_activation', 'fournisseur_epingle', 'jdbc_unix'):
            with self.subTest(cle=cle), self.assertRaises(ValueError):
                v.verifier_resume({**self.resume, cle: False})
        for path in ('/tmp/faux', '/nix/store/' + 'a' * 32 + '-lot/../prive', self.resume['lot'] + ';id'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                v.verifier_resume({**self.resume, 'lot': path})

    def test_autre_uid_source_hors_store_et_unite_manquante_refuses(self):
        for changement in ({'utilisateur': 'root'}, {'executable': '/usr/bin/python3 /tmp/source.py'}):
            r = {**self.resume, 'unites': {**self.resume['unites'],
                'vision-gestion': {**self.resume['unites']['vision-gestion'], **changement}}}
            with self.assertRaises(ValueError): v.verifier_resume(r)
        r = {**self.resume, 'unites': {nom: u for nom, u in self.resume['unites'].items() if nom != 'keycloak'}}
        with self.assertRaises(ValueError): v.verifier_resume(r)

    def test_import_partiel_rotation_personne_ou_autre_candidat_refuses(self):
        for cle in self.rapport:
            r = self.rapport.copy(); del r[cle]
            with self.subTest(cle=cle), self.assertRaises(m.construction.ConstructionRefusee):
                m.preuve_import(r, self.preuve, self.candidat, self.unix, self.build)
        for cle in ('rotation', 'identite_humaine', 'smtp_contacte', 'import_en_base'):
            r = {**self.rapport, cle: True}
            with self.subTest(cle=cle), self.assertRaises(m.construction.ConstructionRefusee):
                m.preuve_import(r, {**self.preuve, cle: True}, self.candidat, self.unix, self.build)
        with self.assertRaises(m.construction.ConstructionRefusee):
            m.preuve_import(self.rapport, self.preuve, {**self.candidat, 'vision': '0' * 40}, self.unix, self.build)

    def test_import_n_execute_pas_main_et_refuse_socket_ou_sqlite(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); root.chmod(0o755)
            script = root / 'synthetique.py'
            prefixe = ['runuser', '-u', 'nobody', '--'] if os.geteuid() == 0 else []
            for code, attendu in (("if __name__=='__main__':raise RuntimeError('service lance')", 0),
                ('import socket; socket.socket().bind(("127.0.0.1",0))', 1),
                ('import sqlite3; sqlite3.connect(":memory:")', 1)):
                if script.exists(): script.chmod(0o600)
                script.write_text(code); script.chmod(0o444)
                r = subprocess.run([*prefixe, sys.executable, '-I', '-c', v.IMPORTS,
                    str(script), 'synthetique'], capture_output=True)
                self.assertEqual(r.returncode, attendu)
                if attendu == 0: self.assertEqual(r.stdout, b'imports_ok\n')

    def test_workflow_garde_le_socle_exact(self):
        path = ROOT / '.github/workflows/vision-mrjam-composants-construire.yml'
        texte = path.read_text()
        self.assertEqual(texte.count('nixpkgs=' + self.candidat['audit']['nixpkgs']), 2)
        self.assertIn('workflow_dispatch:', texte)
        self.assertNotIn('  push:', texte)
        self.assertIn('python3 scripts/ci-exacte.py', texte)
        self.assertIn('--controler', texte)


if __name__ == '__main__': unittest.main()
