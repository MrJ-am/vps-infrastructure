"""Refus des comptes étrangers et preuves incomplètes ; attente sans mutation."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def charger(nom):
    s = importlib.util.spec_from_file_location(nom, ROOT/'scripts'/(nom+'.py'))
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


m = charger('identite-proprietaire-observer')
notes = charger('identite-session-proprietaire')
operateur = charger('vision-proprietaire-enroler')
plan = charger('vision-plan')


class Observation(unittest.TestCase):
    def setUp(self):
        self.sujet = '11111111-1111-4111-8111-111111111111'
        self.client = '22222222-2222-4222-8222-222222222222'
        self.contact = dict(courriel='personne@example.test', nom_connexion='PersonneTest')
        self.ids = dict(pwd=['execution-pwd'], otp=['execution-otp'])
        self.etat = {'compte.json': dict(issuer=m.ISSUER, sujet=self.sujet, **self.contact),
            'creation-demandee': {}, 'courriel-demande': {}, 'courriel-accepte': {},
            'executions.json': self.ids}
        self.base = '/admin/realms/mrjam'
        self.chemin = self.base+'/users/'+self.sujet
        self.api_data = {self.base+'/users?max=2': [dict(id=self.sujet)],
            self.chemin: dict(id=self.sujet, email=self.contact['courriel'], username='personnetest',
                enabled=True, emailVerified=True, requiredActions=[]),
            self.chemin+'/credentials': [dict(type='password'), dict(type='otp')],
            self.base+'/clients?clientId=realm-management': [dict(id=self.client)],
            self.chemin+'/role-mappings/clients/'+self.client+'/composite': []}
        self.appels = []

    def api(self, chemin, *args):
        self.assertEqual(args, ())
        self.appels.append(chemin)
        return self.api_data[chemin]

    def test_sujet_durable_exact_et_requetes_uniquement_get(self):
        original = copy.deepcopy(self.etat)
        self.assertEqual(m.verifier_compte(self.api, self.contact, self.etat, self.ids), self.sujet)
        self.assertEqual(self.etat, original)
        self.assertEqual(len(self.appels), 5)

    def test_recu_absent_ou_subject_etranger_refuse_avant_api(self):
        for key in ('creation-demandee', 'courriel-demande', 'courriel-accepte', 'executions.json'):
            with self.subTest(key=key):
                etat = copy.deepcopy(self.etat); etat.pop(key)
                with self.assertRaises(ValueError): m.verifier_compte(self.api, self.contact, etat, self.ids)
        for key, value in (('sujet', 'inconnu'), ('issuer', 'https://autre.test'), ('courriel', 'autre@example.test'),
                           ('nom_connexion', 'AutreCompte')):
            with self.subTest(key=key):
                etat = copy.deepcopy(self.etat); etat['compte.json'][key] = value
                with self.assertRaises(ValueError): m.verifier_compte(self.api, self.contact, etat, self.ids)
        self.assertEqual(self.appels, [])

    def test_second_compte_ou_mfa_incomplet_ou_admin_identite_refuses(self):
        original = copy.deepcopy(self.api_data)
        cas = [(self.base+'/users?max=2', [dict(id=self.client)]),
               (self.base+'/users?max=2', [dict(id=self.sujet), dict(id=self.client)]),
               (self.chemin+'/credentials', [dict(type='password')]),
               (self.chemin+'/credentials', [dict(type='password'), dict(type='otp'), dict(type='otp')]),
               (self.chemin+'/role-mappings/clients/'+self.client+'/composite', [dict(name='manage-users')])]
        cas += [(self.chemin, {**original[self.chemin], key: value}) for key, value in
                (('id', self.client), ('email', 'autre@example.test'), ('enabled', False),
                 ('emailVerified', False), ('requiredActions', ['CONFIGURE_TOTP']))]
        for chemin, value in cas:
            with self.subTest(chemin=chemin, value=value):
                self.api_data = copy.deepcopy(original); self.api_data[chemin] = value
                with self.assertRaises(ValueError): m.verifier_compte(self.api, self.contact, self.etat, self.ids)

    def preuve(self, date, methodes=None):
        return dict(authMethod='openid-connect', notes={'AUTH_TIME': str(date),
            'authenticators-completed': json.dumps(methodes or {'execution-pwd': date, 'execution-otp': date})})

    def test_presence_credentials_ne_remplace_pas_connexion_et_timeout_sans_preuve(self):
        pauses = []; temps = [0]
        def pause(secondes): pauses.append(secondes); temps[0] += secondes
        for preuves in ([], [self.preuve(100, {'execution-courriel': 100, 'execution-otp': 100})],
                        [self.preuve(100, {'execution-pwd': 100})], [self.preuve(-201)]):
            temps[0] = 0
            r = m.attendre_connexion(lambda: preuves, notes.verifier_notes, self.ids, maximum=10,
                horloge=lambda: 100, monotone=lambda: temps[0], pause=pause)
            self.assertIsNone(r)
        self.assertTrue(all(0 < p <= 5 for p in pauses))

    def test_attente_ne_rejoue_que_lecture_et_accepte_connexion_effective_fraiche(self):
        temps = [0]; appels = []
        def lire():
            appels.append(True)
            return [self.preuve(100)] if temps[0] >= 5 else []
        def pause(secondes): temps[0] += secondes
        self.assertEqual(m.attendre_connexion(lire, notes.verifier_notes, self.ids, maximum=10,
            horloge=lambda: 100, monotone=lambda: temps[0], pause=pause), 100)
        self.assertEqual(len(appels), 2)

    def test_sql_refuse_ou_projection_inconnue_ne_sont_pas_reessayes(self):
        for sortie in (None, {}, [self.preuve(100)]*33):
            with self.subTest(sortie=type(sortie).__name__), self.assertRaises(ValueError):
                m.attendre_connexion(lambda: sortie, notes.verifier_notes, self.ids, maximum=0)
        for maximum in (-1, 601, True, '600'):
            with patch.object(m, 'time') as appel, self.assertRaises(ValueError):
                m.attendre_connexion(lambda: [], notes.verifier_notes, self.ids, maximum=maximum)

    def test_api_observation_interdit_tout_body_et_methode_mutante_avant_reseau(self):
        api = operateur.ApiPrivee('jeton-synthetique', lecture_seule=True)
        with patch.object(api.opener, 'open') as appel:
            for body, method in (({}, None), (None, 'POST'), ([], 'PUT'), (None, 'DELETE'), (None, 'PATCH')):
                with self.subTest(method=method), self.assertRaises(ValueError): api(self.chemin, body, method)
            appel.assert_not_called()

    def test_plan_observation_ferme_interdit_options_et_commandes(self):
        self.assertEqual(plan.verifier(dict(version=1, action='proprietaire-observer')), 'proprietaire-observer')
        for p in (dict(version=1, action='proprietaire-observer', commande='inconnue'),
                  dict(version=1, action='proprietaire-observer;inconnue')):
            with self.assertRaises(ValueError): plan.verifier(p)


if __name__ == '__main__': unittest.main()
