"""Un rapport privé manquant ou un candidat différent ne prépare aucun import."""
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('import_identite', ROOT / 'scripts/vision-identite-import-preparer.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)


class PreuveUnix(unittest.TestCase):
    def setUp(self):
        self.preuve = json.loads((ROOT / 'operations/vision-identite-unix-qualification.json').read_text())
        self.build = json.loads((ROOT / 'operations/vision-identite-construction.json').read_text())
        self.candidat = json.loads((ROOT / 'operations/vision-multiutilisateur-candidat.json').read_text())
        self.rapport = {k: v for k, v in self.preuve.items() if k not in
            ('run', 'job', 'socle_inchange', 'services_actifs', 'sondes_http_tls', 'nouvelle_connexion_ssh')}

    def test_preuve_reelle_coherente(self):
        m.preuve_unix(self.rapport, self.preuve, self.candidat, self.build)

    def test_preuve_partielle_different_paquet_ou_activation_refuses(self):
        for cle in self.rapport:
            with self.subTest(cle=cle), self.assertRaises(m.construction.ConstructionRefusee):
                r = self.rapport.copy(); del r[cle]
                m.preuve_unix(r, self.preuve, self.candidat, self.build)
        for cle in ('activation', 'inscriptions', 'autre_uid_refuse', 'peer_sans_mot_de_passe', 'dynamic_user'):
            r = {**self.rapport, cle: not self.rapport[cle]}
            with self.subTest(cle=cle), self.assertRaises(m.construction.ConstructionRefusee):
                m.preuve_unix(r, {**self.preuve, cle: r[cle]}, self.candidat, self.build)
        with self.assertRaises(m.construction.ConstructionRefusee):
            m.preuve_unix(self.rapport, self.preuve, {**self.candidat, 'vision': '0' * 40}, self.build)

    def test_workflow_utilise_le_socle_exact_et_ses_controles(self):
        contenu = (ROOT / '.github/workflows/vision-identite-import-preparer.yml').read_text()
        self.assertEqual(contenu.count('nixpkgs=' + self.candidat['audit']['nixpkgs']), 2)
        self.assertIn('workflow_dispatch:', contenu)
        self.assertNotIn('  push:', contenu)
        self.assertIn('python3 scripts/ci-exacte.py', contenu)
        self.assertIn('group: vps-administration', contenu)
        self.assertIn('--controler', contenu)
        self.assertNotIn('/var/lib/mrjam-identite/mrjam-realm.json', contenu)


if __name__ == '__main__': unittest.main()
