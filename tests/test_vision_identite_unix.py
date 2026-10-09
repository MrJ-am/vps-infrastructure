"""Refuser une preuve incohérente et arrêter les deux unités après incident."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('unix', ROOT / 'scripts/vision-identite-unix-qualifier.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)


class Qualification(unittest.TestCase):
    def setUp(self):
        self.preuve = json.loads((ROOT / 'operations/vision-identite-construction.json').read_text())
        self.rapport = {k: v for k, v in self.preuve.items() if k not in
            ('run', 'job', 'services_actifs', 'sondes_http_tls', 'nouvelle_connexion_ssh')}
        self.candidat = json.loads((ROOT / 'operations/vision-multiutilisateur-candidat.json').read_text())
        self.resume = dict(version='26.7.3', paquet=self.preuve['paquet'], jdbc_unix=True,
            preconditions_validees=False, inscriptions=False, activation=False)

    def test_preuve_reelle_coherente(self):
        m.preuve_construction(self.rapport, self.preuve, self.candidat, self.resume)

    def test_rapport_partiel_ou_autre_paquet_refuse(self):
        for k in self.rapport:
            with self.subTest(k=k), self.assertRaises(m.construction.ConstructionRefusee):
                r = self.rapport.copy(); del r[k]
                m.preuve_construction(r, self.preuve, self.candidat, self.resume)
        for k, v in (('paquet', '/nix/store/' + 'a'*32 + '-keycloak'), ('version', '26.7.2'),
                ('preconditions_validees', True), ('jdbc_unix', False), ('inscriptions', True)):
            with self.subTest(k=k), self.assertRaises(m.construction.ConstructionRefusee):
                m.preuve_construction(self.rapport, self.preuve, self.candidat, {**self.resume, k: v})

    def test_les_deux_arrets_sont_tentes_apres_un_timeout(self):
        appels = []
        def executer(args, **kw):
            appels.append(args)
            if args[:2] == ['systemctl', 'stop'] and args[2] == 'idp.service':
                raise subprocess.TimeoutExpired(args, 45)
            return subprocess.CompletedProcess(args, 0, stdout=b'0\n')
        with patch.object(m.subprocess, 'run', side_effect=executer), self.assertRaises(m.construction.ConstructionRefusee):
            m.arreter(['idp.service', 'pg.service'], [])
        self.assertIn(['systemctl', 'stop', 'pg.service'], appels)

    def test_pas_de_reussite_si_processus_ou_runtime_reste(self):
        with patch.object(m.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, stdout=b'42\n')):
            with self.assertRaises(m.construction.ConstructionRefusee): m.arreter(['idp.service'], [])
        with tempfile.TemporaryDirectory() as d, patch.object(m.subprocess, 'run',
                return_value=subprocess.CompletedProcess([], 0, stdout=b'0\n')):
            with self.assertRaises(m.construction.ConstructionRefusee): m.arreter(['pg.service'], [Path(d)])


if __name__ == '__main__': unittest.main()
