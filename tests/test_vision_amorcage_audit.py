"""La classification technique ne recopie ni unité inconnue ni données privées."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def charger(nom):
    s = importlib.util.spec_from_file_location(nom, ROOT/'scripts'/(nom+'.py'))
    m = importlib.util.module_from_spec(s);s.loader.exec_module(m);return m


audit = charger('vision-identite-amorcage-auditer')
plan = charger('vision-plan')


class Audit(unittest.TestCase):
    def test_sortie_sans_fragment_prive_et_avec_unites_connues(self):
        secret = 'valeur-utilisateur-confidentielle'
        r = audit.classer('RuntimeError: Dry-activate annonce une unité étrangère '+secret,
            'would activate the configuration...\nwould restart the following units: nscd.service, '+secret+'.service\n')
        self.assertEqual(r['categories'],['unite_etrangere'])
        self.assertEqual(r['unites']['restart'],dict(connues=['nscd.service'],acme=0,inconnues=1))
        self.assertNotIn(secret,json.dumps(r))

    def test_diagnostic_inconnu_et_acme_ne_fuient_pas(self):
        r = audit.classer('trace-privee-indeterminee','would reload the following units: acme-domaine-prive.service\n')
        self.assertEqual(r['categories'],[]);self.assertEqual(r['unites']['reload'],dict(connues=[],acme=1,inconnues=0))
        self.assertNotIn('domaine-prive',json.dumps(r))

    def test_lecture_refuse_liens_droits_taille_et_type(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/'prive';p.write_text('texte');p.chmod(0o600)
            self.assertEqual(audit.lire(p),'texte')
            lien = Path(tmp)/'lien';lien.symlink_to(p)
            with self.assertRaises(OSError): audit.lire(lien)
            os.link(p,Path(tmp)/'dur')
            with self.assertRaises(ValueError): audit.lire(p)
            (Path(tmp)/'dur').unlink();p.chmod(0o644)
            with self.assertRaises(ValueError): audit.lire(p)
            p.chmod(0o600);p.write_bytes(b'x'*262145)
            with self.assertRaises(ValueError): audit.lire(p)
            fifo = Path(tmp)/'fifo';os.mkfifo(fifo,0o600)
            with self.assertRaises(ValueError): audit.lire(fifo)

    def test_plan_n_admet_aucun_parametre_ou_commande(self):
        for action in ('amorcage','diagnostic'):
            self.assertEqual(plan.verifier(dict(version=1,action=action)),action)
        for valeur in (dict(version=True,action='amorcage'),dict(version=1,action='shell'),
                dict(version=1,action='diagnostic',commande='libre'),dict(version=1,action='diagnostic\nautre=oui')):
            with self.assertRaises(ValueError):plan.verifier(valeur)


if __name__ == '__main__': unittest.main()
