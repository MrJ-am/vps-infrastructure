"""La preuve durable ne prétend pas à une session fraîche aujourd'hui."""
from datetime import datetime
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


def charger(nom):
    s = importlib.util.spec_from_file_location(nom, ROOT/'scripts'/(nom+'.py'))
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


m = charger('vision-bascule-principaux')
acl = charger('vision-acl')
plan = charger('vision-plan')


class Principaux(unittest.TestCase):
    def setUp(self):
        self.public = json.loads((ROOT/'operations/vision-proprietaire-observation.json').read_text())
        self.sujet = '11111111-1111-4111-8111-111111111111'
        self.compte = dict(issuer=m.ISSUER, sujet=self.sujet)
        self.date = int(datetime.fromisoformat(self.public['fin'].replace('Z', '+00:00')).timestamp())-15
        self.nom = 'connexion-'+str(self.date)+'.json'
        self.preuve = dict(version=1, issuer=m.ISSUER, sujet=self.sujet, pwd_otp_frais=True, date=self.date)
        self.preuves = {self.nom: self.preuve}

    def test_preuve_exacte_durable_sans_fraicheur_inventee(self):
        r = m.verifier_preuve(self.public, self.compte, self.preuves)
        self.assertEqual(r, dict(issuer=m.ISSUER, sujet=self.sujet, possession_verifiee_a=self.date))
        self.assertNotIn('pwd_otp_frais', r)

    def test_autre_sujet_ou_receipt_ou_methode_refuses(self):
        for key, value in (('sujet', '22222222-2222-4222-8222-222222222222'),
                           ('issuer', 'https://etranger.test'), ('pwd_otp_frais', False), ('date', True),
                           ('date', 1760050000), ('date', 1760059999), ('version', True)):
            with self.subTest(key=key), self.assertRaises(ValueError):
                m.verifier_preuve(self.public, self.compte, {**self.preuves, self.nom: {**self.preuve, key:value}})
        for key, value in (('infrastructure', 'a'*40), ('execution', 1), ('job', 1),
                           ('recu_prive_ecrit', False), ('pwd_otp_frais_au_controle', False),
                           ('inscriptions', True), ('privilege_administrateur_identite', True)):
            with self.subTest(key=key), self.assertRaises(ValueError):
                m.verifier_preuve({**self.public, key:value}, self.compte, self.preuves)

    def test_recu_manquant_double_ou_nom_ambigu_refuses(self):
        for preuves in ({}, {'connexion-1760051301.json': self.preuve},
                        {**self.preuves, 'connexion-1760051301.json': self.preuve}):
            with self.subTest(preuves=list(preuves)), self.assertRaises(ValueError):
                m.verifier_preuve(self.public, self.compte, preuves)

    def test_preparation_exige_unique_identifiant_historique(self):
        identite = m.verifier_preuve(self.public, self.compte, self.preuves)
        historique = dict(utilisateur_historique='owner-test', proprietaires=1, authentification_unique=True)
        sql = m.association_sql(identite, historique, acl.litteral)
        self.assertIn("VALUES('"+m.ISSUER+"','"+self.sujet+"','owner-test')", sql)
        for key, value in (('proprietaires', 2), ('authentification_unique', False),
                           ('utilisateur_historique', "owner';DROP TABLE contenu;--")):
            with self.subTest(key=key), self.assertRaises(ValueError):
                m.association_sql(identite, {**historique, key:value}, acl.litteral)

    def test_aucun_socket_production_et_cluster_incorrect_refuses(self):
        socket = '/var/lib/postgresql/vision-bascule-'+'a'*12
        r = dict(tcp='',socket=socket,data=socket+'/data',encodage='UTF8',majeure=17)
        m.verifier_isole(socket, r)
        for p in ('/run/postgresql', '/run/mrjam-amorcage-postgresql', socket+'/../17', '/tmp/isole'):
            with self.subTest(path=p), self.assertRaises(ValueError): m.verifier_isole(p,r)
        for key, value in (('tcp','127.0.0.1'), ('data','/var/lib/postgresql/17'), ('encodage','SQL_ASCII'), ('majeure',18)):
            with self.subTest(key=key), self.assertRaises(ValueError): m.verifier_isole(socket,{**r,key:value})

    def test_plan_dedie_ferme_sans_commande_libre(self):
        self.assertEqual(plan.verifier(dict(version=1,action='vision-preparer')), 'vision-preparer')
        self.assertEqual(plan.verifier(dict(version=1,action='vision-diagnostic')), 'vision-diagnostic')
        with self.assertRaises(ValueError): plan.verifier(dict(version=1,action='vision-preparer',commande='inconnue'))


if __name__ == '__main__': unittest.main()
