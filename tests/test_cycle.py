"""Échec/reprise d'un effacement : pas de SQL avant la copie chiffrée externe."""
import importlib.util
import json
from pathlib import Path
import smtplib
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'services/mrjam-courriel'))
spec=importlib.util.spec_from_file_location('vision_cycle',ROOT/'services/vision-cycle/cycle.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
CONFIG=dict(host='smtp.protonmail.ch',port=587,username='synthetique@example.test',
            password='JetonSynthetique123',from_address='synthetique@example.test',
            starttls_required=True,certificate_verification=True)


class Cycle(unittest.TestCase):
    def test_intention_persiste_et_reprise_sans_double_effacement(self):
        with tempfile.TemporaryDirectory() as root:
            cycle=module.Cycle('dsn-synthetique',root,CONFIG,
                dict(adresse_exploitant='exploitant@example.test',recipient_age='age1'+'a'*58),'secret-synthetique')
            appels=[]
            def sql(op,*args):
                appels.append((op,args));return {'efface':True}
            cycle.sql=sql
            def indisponible(*args):raise smtplib.SMTPServerDisconnected()
            cycle.file.transport=indisponible
            with patch.object(module,'archiver_effacement',wraps=module.archiver_effacement), patch('courriel.chiffrer_effacement',return_value=b'piece-chiffree-synthetique'):
                r=cycle.effacer('compte-synthetique','EFFACER VISION')
                self.assertTrue(r['effacement_en_attente']);self.assertEqual(appels,[])
                registre=Path(root)/'effacements.jsonl'
                self.assertEqual(registre.stat().st_mode&0o077,0)
                avant=registre.read_bytes()
                cycle.file.transport=lambda *_:None
                # Lever la temporisation synthétique de la première erreur.
                with cycle.file.ouvrir() as db:db.execute('UPDATE courriels SET prochain=0')
                self.assertTrue(cycle.effacer('compte-synthetique','EFFACER VISION')['efface'])
                self.assertEqual(registre.read_bytes(),avant)
                self.assertEqual([a[0] for a in appels],['effacer'])
                self.assertTrue(cycle.effacer('compte-synthetique','EFFACER VISION')['efface'])
                self.assertEqual(len(appels),1)

    def test_annulation_ou_delai_non_ecoule_ne_cree_aucune_intention(self):
        with tempfile.TemporaryDirectory() as root:
            cycle=module.Cycle('dsn-synthetique',root,CONFIG,
                dict(adresse_exploitant='exploitant@example.test',recipient_age='age1'+'a'*58),'secret-synthetique')
            cycle.sql=lambda *_:False
            with self.assertRaises(ValueError):cycle.effacer('compte-synthetique','EFFACER VISION','id-preavis')
            self.assertFalse((Path(root)/'effacements.jsonl').exists())


if __name__=='__main__':unittest.main()
