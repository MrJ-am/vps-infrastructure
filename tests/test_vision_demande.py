"""Refus des déclenchements étrangers et des faux rapports de progression."""
import copy
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def charger(nom):
    spec = importlib.util.spec_from_file_location(nom, ROOT/'scripts'/(nom+'.py'))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module


demande = charger('vision-demande-verifier')
avancement = charger('vision-avancement')
amorcage = charger('vision-identite-amorcage-activer')
SHA = 'a'*40


class Demandes(unittest.TestCase):
    def setUp(self):
        self.env = dict(GITHUB_REPOSITORY=demande.DEPOT, GITHUB_SHA=SHA,
            GITHUB_EVENT_NAME='workflow_run', GITHUB_REF='refs/heads/main')
        self.evenement = dict(repository=dict(full_name=demande.DEPOT), workflow_run=dict(
            event='push', head_branch=demande.BRANCHE, head_sha=SHA, status='completed',
            conclusion='success', path='.github/workflows/vision-demande.yml',
            repository=dict(full_name=demande.DEPOT), head_repository=dict(full_name=demande.DEPOT)))
        self.main = dict(ref='refs/heads/main', object=dict(type='commit', sha=SHA))

    def test_demande_dediee_exacte_et_lancement_manuel_main(self):
        self.assertTrue(demande.verifier(self.env, self.evenement, self.main)['demande_validee'])
        self.env.update(GITHUB_EVENT_NAME='workflow_dispatch', GITHUB_REF='refs/heads/main')
        self.evenement['inputs'] = {}
        self.assertTrue(demande.verifier(self.env, self.evenement, self.main)['demande_validee'])
        self.evenement['inputs'] = {'commande': 'autre'}
        with self.assertRaises(ValueError): demande.verifier(self.env, self.evenement, self.main)

    def test_push_main_pr_fork_et_branche_etrangere_refuses(self):
        for cle, valeur in (('GITHUB_REF', 'refs/heads/operations/vision'), ('GITHUB_REF', 'refs/heads/autre'),
                ('GITHUB_EVENT_NAME', 'pull_request'), ('GITHUB_EVENT_NAME', 'push'),
                ('GITHUB_REPOSITORY', 'autre/depot'), ('GITHUB_SHA', 'a'*39+';')):
            env = self.env | {cle: valeur}
            with self.subTest(cle=cle,valeur=valeur), self.assertRaises(ValueError):
                demande.verifier(env, self.evenement, self.main)
        evenement = copy.deepcopy(self.evenement); evenement['repository']['full_name'] = 'autre/depot'
        with self.assertRaises(ValueError): demande.verifier(self.env, evenement, self.main)

    def test_signal_etranger_echoue_ou_non_exact_et_main_avance_refuses(self):
        for cle, valeur in (('event', 'pull_request'), ('head_branch', 'main'), ('head_sha', 'b'*40),
                ('status', 'in_progress'), ('conclusion', 'failure'), ('path', '.github/workflows/autre.yml'),
                ('head_repository', dict(full_name='autre/fork')), ('repository', dict(full_name='autre/fork'))):
            evenement = copy.deepcopy(self.evenement); evenement['workflow_run'][cle] = valeur
            with self.subTest(cle=cle), self.assertRaises(ValueError):
                demande.verifier(self.env, evenement, self.main)
        for modifie in (dict(ref='autre', object=self.main['object']),
                dict(ref='refs/heads/main', object=dict(type='commit', sha='b'*40)),
                dict(ref='refs/heads/main', object=dict(type='tag', sha=SHA))):
            with self.assertRaises(ValueError): demande.verifier(self.env, self.evenement, modifie)

    def test_rapport_non_prouve_ne_devient_pas_un_succes(self):
        with patch.dict(os.environ, {'GITHUB_SHA': SHA}):
            for rapport in (dict(infrastructure='b'*40,enregistre=True),
                    dict(infrastructure=SHA,enregistre='true'), dict(infrastructure=SHA)):
                with self.assertRaises(ValueError): avancement.resume(rapport)
            rapport = dict(infrastructure=SHA, activation_reservee=True, generation_enregistree=True,
                retour_autonome=True, retour_neutralise=True, copie_locale_chiffree=True,
                postgres_prive=True, services_conserves=True, identite_humaine=False,
                mode_vision_oidc=False, inscriptions=False)
            self.assertIn('Les inscriptions sont fermées', avancement.resume(rapport, True))
            for cle, valeur in (('services_conserves', False), ('inscriptions', True), ('identite_humaine', True)):
                with self.subTest(cle=cle), self.assertRaises(ValueError):
                    avancement.resume(rapport | {cle: valeur}, True)

    def test_reprise_refuse_tentative_entamee_sans_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            essai = amorcage.Essai.__new__(amorcage.Essai); essai.d = Path(tmp); essai.revision = SHA
            essai.marque = lambda nom: (essai.d/nom).exists(); essai.candidat = {}
            for nom in ('plan.json', 'commence', 'echec', 'retour-commence', 'retour-termine'):
                (essai.d/nom).touch()
                with self.subTest(nom=nom), patch.object(amorcage.construction, 'verifier_socle') as socle:
                    with self.assertRaises(RuntimeError): essai.statut()
                    socle.assert_not_called()
                (essai.d/nom).unlink()

    def test_marqueur_seul_ne_prouve_pas_enregistrement(self):
        essai = amorcage.Essai.__new__(amorcage.Essai); essai.revision = SHA; essai.nouveau = '/nix/store/attendu'
        essai.marque = lambda nom: nom == 'enregistre'
        essai.lire = lambda nom: dict(infrastructure='b'*40,systeme_amorcage=essai.nouveau,generation_enregistree=True)
        with patch.object(essai, 'verifier_local') as controles:
            with self.assertRaises(RuntimeError): essai.statut()
            controles.assert_not_called()


if __name__ == '__main__': unittest.main()
