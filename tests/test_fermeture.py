"""Intention minimale persistante, envoi chiffré puis effacements aveugles."""
import importlib.util
import json
from pathlib import Path
import smtplib
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'services/mrjam-courriel'))
spec=importlib.util.spec_from_file_location('fermeture',ROOT/'services/mrjam-fermeture/fermeture.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
SMTP=dict(host='smtp.protonmail.ch',port=587,username='synthetique@example.test',password='JetonSynthetique123',
          from_address='synthetique@example.test',starttls_required=True,certificate_verification=True)


class Fermeture(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.app=m.Fermeture('dsn',self.tmp.name,SMTP,
            {'adresse_exploitant':'exploitant@example.test','recipient_age':'age1'+'a'*58},'secret-client','secret-hook')
        self.app.file.transport=lambda *_:None
        self.appels=[]
        def sql(op,sujet):
            self.appels.append((op,sujet));return ['compte-vision'] if op=='comptes' else {'efface':True}
        self.app.sql=sql

    def test_echec_mail_puis_reprise_sans_effacement_premature(self):
        def erreur(*_):raise smtplib.SMTPServerDisconnected()
        self.app.file.transport=erreur
        with patch.object(m.subprocess,'run') as age, patch.object(m.requests,'post') as admission:
            age.return_value.stdout=b'chiffre-age'
            self.assertFalse(self.app.preparer('sujet','FERMER MON COMPTE'))
            admission.assert_not_called();self.assertEqual([op for op,_ in self.appels],['comptes'])
            registre=(Path(self.tmp.name)/'effacements.jsonl').read_bytes()
            p=json.loads(registre);self.assertEqual(set(p),{'version','type','emetteur','sujet','confirmee_a','outils'})
            self.app.file.transport=lambda *_:None
            with self.app.file.ouvrir() as db:db.execute('UPDATE courriels SET prochain=0')
            self.assertTrue(self.app.preparer('sujet','FERMER MON COMPTE'))
            self.assertEqual((Path(self.tmp.name)/'effacements.jsonl').read_bytes(),registre)
            self.assertEqual(age.call_count,1)
            self.assertTrue(self.app.preparer('sujet','FERMER MON COMPTE'))
            self.assertEqual([op for op,_ in self.appels],['comptes','effacer'])
            self.assertEqual(admission.call_count,1)

    def test_apres_vision_effacee_compte_commun_toujours_fermable(self):
        self.app.sql=lambda op,_:[] if op=='comptes' else {'efface':True}
        with patch.object(m.subprocess,'run') as age, patch.object(m.requests,'post'):
            age.return_value.stdout=b'chiffre-age'
            self.assertTrue(self.app.preparer('identite-sans-vision','FERMER MON COMPTE'))
        p=json.loads((Path(self.tmp.name)/'effacements.jsonl').read_text())
        self.assertEqual(p['outils'],{'vision':[]})

    def test_confirmation_et_schema_limites_sans_contenu(self):
        with self.assertRaises(ValueError):self.app.preparer('sujet','oui')
        self.assertFalse((Path(self.tmp.name)/'effacements.jsonl').exists())
        p={'version':2,'type':'fermeture_commune','emetteur':m.ISSUER,'sujet':'sujet','confirmee_a':1,'outils':{'vision':[]}}
        self.assertEqual(m.verifier_registre(p),p)
        for faux in ({**p,'courriel':'secret@example.test'},{**p,'outils':{'inconnu':[]}},{**p,'emetteur':'https://inconnu.test'}):
            with self.assertRaises(ValueError):m.verifier_registre(faux)

    @unittest.skipUnless(shutil.which('age') and shutil.which('age-keygen'),'age requis')
    def test_registre_communal_chiffre_dans_courriel_reel(self):
        cle=Path(self.tmp.name)/'cle.age'
        subprocess.run(['age-keygen','-o',str(cle)],check=True,stderr=subprocess.DEVNULL)
        recipient=subprocess.check_output(['age-keygen','-y',str(cle)],text=True).strip()
        self.app.config['recipient_age']=recipient;messages=[]
        self.app.file.transport=lambda _,message:messages.append(message)
        with patch.object(m.requests,'post'):
            self.assertTrue(self.app.preparer('sujet-secret','FERMER MON COMPTE'))
        courrier=messages[0];self.assertNotIn(b'sujet-secret',courrier.as_bytes())
        chiffre=list(courrier.iter_attachments())[0].get_payload(decode=True)
        clair=subprocess.check_output(['age','-d','-i',str(cle)],input=chiffre,stderr=subprocess.DEVNULL)
        p=json.loads(clair);self.assertEqual(p['sujet'],'sujet-secret')
        self.assertEqual(p['outils'],{'vision':['compte-vision']});m.verifier_registre(p)


if __name__=='__main__':unittest.main()
