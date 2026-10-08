"""Aucun compte avant les confirmations et le contrôle requis ; liens à usage unique."""
from contextlib import closing
from email import message_from_bytes
import importlib.util
from pathlib import Path
import re
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'services/mrjam-courriel'))
spec = importlib.util.spec_from_file_location('admission', ROOT/'services/mrjam-admission/admission.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
SMTP = dict(host='smtp.protonmail.ch', port=587, username='synthetique@example.test',
            password='JetonSynthetique123', from_address='synthetique@example.test',
            starttls_required=True, certificate_verification=True)


class Admission(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.app = m.Admission('dsn-synthetique', self.tmp.name, SMTP, 'secret-synthetique')
        self.app.file.transport = lambda *_: None
        self.sql = []; self.app.sql = lambda op, *args: self.sql.append((op, args))
        self.p = dict(invitation='a'*43, notice='test', courriel='jeune@example.test', pays='France',
                      age='moins15', parent='parent@example.test', pseudonyme='Test')

    def liens(self):
        with closing(self.app.file.ouvrir()) as db:
            messages = db.execute('SELECT cle,message FROM courriels ORDER BY cle').fetchall()
        return {cle.split(':')[0]: re.search(r'/admission#([A-Za-z0-9_-]{43})',
                message_from_bytes(contenu).get_payload(decode=True).decode()).group(1)
                for cle, contenu in messages if cle.split(':')[0] in ('admission', 'parent')}

    def demande(self):
        self.app.demander(self.p)
        with closing(self.app.ouvrir()) as db:
            return dict(db.execute('SELECT * FROM demandes').fetchone())

    def test_accord_mail_ne_suffit_pas_et_confirmation_expresse(self):
        d = self.demande(); tokens = self.liens()
        self.assertEqual(self.app.apercu(tokens['parent']), {'type': 'parent'})
        with self.assertRaisesRegex(ValueError, 'confirmation_requise'):
            self.app.confirmer(tokens['parent'])
        self.app.confirmer(tokens['parent'], True)
        self.app.confirmer(tokens['admission'], True)
        with patch.object(self.app, 'provisionner') as creation:
            self.app.traiter(); creation.assert_not_called()
            self.app.approuver(d['id'], 'entretien', 'Référence minimale synthétique',
                              'https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000037823135')
            self.app.traiter(); creation.assert_called_once()
        for token in tokens.values():
            with self.assertRaisesRegex(ValueError, 'lien_invalide'):
                self.app.confirmer(token, True)
        self.assertNotIn(tokens['parent'], Path(self.app.chemin).read_bytes().decode(errors='ignore'))

    def test_adulte_france_et_autres_pays(self):
        for pays, age, controle in [('France', 'majeur', False), ('France', '15a17', True),
                                    ('Allemagne', 'majeur', True), ('Allemagne', 'moins15', True)]:
            with self.subTest(pays=pays, age=age), tempfile.TemporaryDirectory() as root:
                app = m.Admission('dsn', root, SMTP, 'secret'); app.sql = lambda *_: None
                app.file.transport = lambda *_: None
                p = {**self.p, 'pays': pays, 'age': age, 'parent': ''}
                app.demander(p)
                with closing(app.ouvrir()) as db:
                    d = dict(db.execute('SELECT * FROM demandes').fetchone())
                    db.execute('UPDATE demandes SET verifie_a=? WHERE id=?', (int(time.time()), d['id'])); db.commit()
                self.assertEqual(bool(d['manuel']), controle)
                with patch.object(app, 'provisionner') as creation:
                    app.traiter(); self.assertEqual(creation.call_count, 0 if controle else 1)

    def test_parent_absent_ou_meme_adresse_refuse(self):
        for parent in ('', self.p['courriel']):
            with self.assertRaises(ValueError): self.app.demander({**self.p, 'parent': parent})
        self.assertEqual(self.sql, [])

    def test_pas_de_creation_ni_mail_sans_reservation(self):
        self.app.sql = lambda *_: (_ for _ in ()).throw(ValueError('invitation_indisponible'))
        with self.assertRaises(ValueError): self.app.demander(self.p)
        with closing(self.app.file.ouvrir()) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM courriels').fetchone()[0], 0)

    def test_age_pays_sujet_et_parametres_imposes(self):
        for p in ({**self.p, 'sujet': 'vol'}, {**self.p, 'age': 'inconnue'},
                  {**self.p, 'pays': '\nFrance'}, {**self.p, 'courriel': 'a\n@example.test'}):
            with self.assertRaises(ValueError): self.app.demander(p)

    def test_expiration_et_purge(self):
        self.demande(); tokens = self.liens()
        with closing(self.app.ouvrir()) as db, db:
            db.execute('UPDATE demandes SET expire=0')
        with self.assertRaises(ValueError): self.app.confirmer(tokens['admission'], True)
        with patch.object(self.app, 'provisionner') as creation:
            self.app.traiter(); creation.assert_not_called()
        self.assertEqual(self.sql[-1][0], 'annuler')

    def test_demande_repetee_ne_multiplie_pas_courriels(self):
        self.demande(); avant = self.liens()
        self.app.demander(self.p)
        self.assertEqual(self.liens(), avant)
        self.assertEqual([op for op, _ in self.sql], ['reserver'])

    def test_compte_existant_verifie_sans_reinitialisation(self):
        self.p.update(age='majeur', parent='')
        d = self.demande(); identite = {'id': 'sujet-existant', 'email': self.p['courriel'],
                                       'emailVerified': True, 'enabled': True, 'username': 'ancien'}
        class Reponse:
            def raise_for_status(self): pass
            def json(self): return [identite]
        with patch.object(self.app, 'jeton', return_value={}), patch.object(m.requests, 'get', return_value=Reponse()), patch.object(m.requests, 'put') as put:
            self.app.provisionner(d); put.assert_not_called()
        self.assertEqual([op for op, _ in self.sql], ['reserver', 'reserver', 'certifier', 'activer'])
        self.assertEqual(self.sql[-2][1][2], 'sujet-existant')

    def test_identite_non_verifiee_ne_peut_pas_etre_reprise(self):
        self.p.update(age='majeur', parent=''); d = self.demande()
        class Reponse:
            def raise_for_status(self): pass
            def json(self): return [{'id': 'ancien', 'email': self.p['courriel'], 'emailVerified': False}]
        reponse = Reponse(); reponse.p = self.p
        with patch.object(self.app, 'jeton', return_value={}), patch.object(m.requests, 'get', return_value=reponse), patch.object(m.requests, 'put') as put:
            with self.assertRaisesRegex(ValueError, 'identite_indisponible'): self.app.provisionner(d)
            put.assert_not_called()
        self.assertNotIn('certifier', [op for op, _ in self.sql])

    def test_reprise_creation_ne_devient_active_qu_apres_allocation_sql(self):
        self.p.update(age='majeur', parent=''); d = self.demande()
        identite = {'id': 'nouveau', 'email': self.p['courriel'], 'emailVerified': True,
                    'enabled': False, 'username': 'admission-'+d['id']}
        class Reponse:
            def raise_for_status(self): pass
            def json(self): return [identite]
        def sql(op, *args):
            self.sql.append((op, args))
            if op == 'identifier': return {'erreur': 'invitation_requise'}
            if op == 'activer': raise ValueError('invitation_indisponible')
        self.app.sql = sql
        with patch.object(self.app, 'jeton', return_value={}), patch.object(m.requests, 'get', return_value=Reponse()), patch.object(m.requests, 'put') as put:
            with self.assertRaisesRegex(ValueError, 'invitation_indisponible'): self.app.provisionner(d)
            put.assert_not_called()


if __name__ == '__main__': unittest.main()
