"""Contrôles des risques de perte et d'acquittement erroné du registre."""

import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

RACINE = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('coordination', RACINE / 'scripts/coordination.py')
coordination = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(coordination)


class Coordination(unittest.TestCase):
    def setUp(self):
        self.temporaire = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporaire.cleanup)
        self.racine = Path(self.temporaire.name)
        dossier = self.racine / 'coordination'
        dossier.mkdir()
        for nom in ['projets.json', 'CONTRATS.org']:
            shutil.copyfile(RACINE / 'coordination' / nom, dossier / nom)
        debut, _ = coordination.decouper((RACINE / 'coordination/REGISTRE.org').read_text())
        (dossier / 'REGISTRE.org').write_text(debut)
        self.projets, _, self.debut, _, _ = coordination.charger(self.racine)
        self.bloc = ('* Changement de contrat\n' + coordination.proprietes({
            'ID': '20260922-test-abc', 'EMETTEUR': 'vps', 'PORTEE': 'ciblee',
            'DESTINATAIRES': 'vps vision', 'CREE_LE': '2026-01-01T00:00:00+00:00',
            'CONSOLIDATION': 'sans-objet'}) + 'Vision doit adopter le contrat proposé.\n\n')
        for projet in ['vps', 'vision']:
            self.bloc += f'** TODO {projet}\n' + coordination.proprietes(dict.fromkeys(
                ['LU_SHA256', 'LU_LE', 'CONTEXTE', 'PREUVE'], '-')) + '\n'
        self.message = coordination.analyser(self.bloc, self.projets)

    def repondre(self, message, projet, etat='DONE', preuve='Test isolé réussi', commentaire=None):
        return coordination.repondre(message, projet, etat, message['empreinte'],
            self.projets[projet]['depot'] + '@' + 'a' * 40, preuve, commentaire, self.projets)

    def test_lecture_sans_accuse(self):
        coordination.enregistrer(self.racine, self.debut, [self.message])
        chemin = self.racine / 'coordination/REGISTRE.org'
        avant = chemin.read_bytes()
        resultat = subprocess.run(['python3', str(RACINE / 'scripts/coordination.py'),
            '--racine', str(self.racine), 'lire', 'vision'], capture_output=True, text=True, check=True)
        self.assertEqual(avant, chemin.read_bytes())
        self.assertIn(self.message['empreinte'], resultat.stdout)

    def test_destinataire_absent(self):
        with self.assertRaises(ValueError):
            coordination.analyser(self.bloc.split('** TODO vision')[0], self.projets)

    def test_message_global_incomplet(self):
        message = coordination.analyser(self.bloc.replace('PORTEE: ciblee', 'PORTEE: globale'), self.projets)
        coordination.enregistrer(self.racine, self.debut, [message])
        with self.assertRaisesRegex(ValueError, 'tous les projets'):
            coordination.charger(self.racine)

    def test_acquittement_ancien_refuse(self):
        message = self.repondre(self.message, 'vps')
        with self.assertRaisesRegex(ValueError, 'périmé'):
            coordination.analyser(message['bloc'].replace('contrat proposé', 'contrat modifié'), self.projets)

    def test_reponse_sur_lecture_perimee(self):
        with self.assertRaisesRegex(ValueError, 'a changé'):
            coordination.repondre(self.message, 'vps', 'DONE', '0' * 64,
                'MrJ-am/vps-infrastructure@' + 'a' * 40, 'Preuve', None, self.projets)

    def test_lecture_partielle_narchive_pas(self):
        message = self.repondre(self.message, 'vps')
        message = self.repondre(message, 'vision', 'LU')
        self.assertFalse(coordination.eligible(message))
        self.assertEqual([], coordination.archiver(self.racine, self.debut, [message], True))

    def test_done_exige_preuve_et_taches_terminees(self):
        for preuve, commentaire in [('-', None), ('Test', '- [ ] Migration\n'), ('Test', '- [-] Migration\n')]:
            with self.subTest(preuve=preuve, commentaire=commentaire), self.assertRaises(ValueError):
                self.repondre(self.message, 'vision', preuve=preuve, commentaire=commentaire)

    def test_blocage_explique(self):
        with self.assertRaisesRegex(ValueError, 'non expliqué'):
            self.repondre(self.message, 'vision', 'BLOQUE')

    def test_consolidation_requise(self):
        message = coordination.analyser(self.bloc.replace('sans-objet', 'a-faire'), self.projets)
        for projet in ['vps', 'vision']:
            message = self.repondre(message, projet)
        self.assertFalse(coordination.eligible(message))

    def test_archivage_integral_et_idempotent(self):
        message = self.message
        for projet in ['vps', 'vision']:
            message = self.repondre(message, projet)
        coordination.enregistrer(self.racine, self.debut, [message])
        coordination.archiver(self.racine, self.debut, [message], True)
        _, _, debut, messages, archives = coordination.charger(self.racine)
        self.assertEqual([], messages)
        self.assertEqual(message['bloc'], archives[-1]['bloc'])
        self.assertEqual([], coordination.archiver(self.racine, debut, messages, True))

    def test_id_recycle_refuse(self):
        coordination.enregistrer(self.racine, self.debut, [self.message, self.message])
        with self.assertRaisesRegex(ValueError, 'dupliqué'):
            coordination.charger(self.racine)

    def test_suppression_ou_retrait_destinataire_refuses(self):
        coordination.enregistrer(self.racine, self.debut, [self.message])
        def git(*args):
            return subprocess.run(['git', '-C', str(self.racine), *args], check=True, capture_output=True, text=True).stdout.strip()
        git('init')
        git('add', '.')
        git('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-m', 'Référence')
        base = git('rev-parse', 'HEAD')
        with self.assertRaisesRegex(ValueError, 'disparu'):
            coordination.verifier_transition(self.racine, base, [], [], self.projets)
        retire = self.bloc.replace('DESTINATAIRES: vps vision', 'DESTINATAIRES: vps').split('** TODO vision')[0]
        message = coordination.analyser(retire, self.projets)
        with self.assertRaisesRegex(ValueError, 'Destinataire retiré'):
            coordination.verifier_transition(self.racine, base, [message], [], self.projets)


if __name__ == '__main__':
    unittest.main()
