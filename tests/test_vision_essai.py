"""Récupération exigée, artefact fermé et simulation sans unité étrangère."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('essai_qualification',ROOT/'scripts/vision-essai-qualification.py')
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)


class Essai(unittest.TestCase):
    def test_preuve_complete_exterieure_necessaire(self):
        r=json.loads((ROOT/'operations/vision-recuperation-resultat.json').read_text())
        c=json.loads((ROOT/'operations/vision-recuperation-confirmation.json').read_text())
        m.verifier_recuperation(r,c)
        for cle,valeur in [('version',True),('dechiffrement_complet',False),('preuve_aleatoire_verifiee',False),
            ('copie_exterieure_verifiee',False),('preuve_sha256','a'*64),('cle_privee_transmise',True),
            ('chiffre_sha256','b'*64),('execution',38047719442),('cle_publique','age1autre')]:
            d=copy.deepcopy(c);d[cle]=valeur
            with self.subTest(cle=cle),self.assertRaises(ValueError):m.verifier_recuperation(r,d)

    def test_interface_exacte_et_corruption_refusee(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp);r=m.extraire_interface(ROOT/'vendor/vision-multiutilisateur-interface.zip',d/'interface')
            self.assertEqual(len(r['fichiers']),22)
            with self.assertRaises(ValueError):m.extraire_interface(ROOT/'vendor/vision-multiutilisateur-interface.zip',d/'interface')
            p=d/'autre.zip';p.write_bytes(b'archive incorrecte')
            with self.assertRaises(ValueError):m.extraire_interface(p,d/'autre')

    def test_dry_unite_etrangere_et_systemd_refuses(self):
        texte='would restart the following units: vision.service, mrj-auth.service\nwould activate the configuration'
        self.assertEqual(m.verifier_dry(texte),['mrj-auth.service','vision.service'])
        for t in (texte.replace('vision.service','matheval.service'),texte.replace('vision.service','sshd.service'),
            texte+'\nwould restart systemd',texte+'\nwould start the following units: unite-etrangere.service',
            'would restart the following units: vision.service'):
            with self.assertRaises(ValueError):m.verifier_dry(t)

    def test_retour_shell_autonome_syntaxe(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'retour.sh';p.write_text(m.script_retour(Path('/root/vision-bascule-preparations')/('a'*40),
                '/nix/store/'+('b'*32)+'-nixos-system-test',Path('/nix/store/'+('b'*32)+'-nixos-system-test/sw/bin'),
                Path('/nix/store/'+('c'*32)+'-postgresql-17.11'),Path('/nix/store/'+('d'*32)+'-util-linux/bin/runuser'),
                'vision-essai-aaaaaaaaaaaa.service'))
            subprocess.run(['bash','-n',str(p)],check=True)


if __name__=='__main__':unittest.main()
