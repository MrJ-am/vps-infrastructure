"""Rapports privés et plan fermé de l'ouverture par invitation."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def charger(nom):
    s = importlib.util.spec_from_file_location(nom, ROOT / 'scripts' / (nom + '.py'))
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
    return m


m = charger('vision-inscriptions-ouvrir')


class Ouverture(unittest.TestCase):
    def test_plan_ferme_sans_parametre(self):
        p = charger('vision-plan')
        self.assertEqual(p.verifier(dict(version=1, action='vision-inscriptions-ouvrir')), 'vision-inscriptions-ouvrir')
        for v in (dict(version=True, action='vision-inscriptions-ouvrir'),
                  dict(version=1, action='vision-inscriptions-ouvrir', lien='invalide'),
                  dict(version=1, action='commande-libre')):
            with self.assertRaises(ValueError): p.verifier(v)

    @unittest.skipUnless(os.geteuid() == 0, 'Qualification native de rapports root')
    def test_rapport_root_borne_sans_lien_ni_partage(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'rapport.json'
            p.write_text(json.dumps(dict(synthetique=True))); p.chmod(0o600)
            self.assertEqual(m.lire(p), dict(synthetique=True))
            lien = Path(d) / 'lien'; lien.symlink_to(p)
            with self.assertRaises(OSError): m.lire(lien)
            partage = Path(d) / 'partage'; os.link(p, partage)
            with self.assertRaises(ValueError): m.lire(p)
            partage.unlink(); p.chmod(0o640)
            with self.assertRaises(ValueError): m.lire(p)
            p.chmod(0o600); p.write_text('x' * 1048577)
            with self.assertRaises(ValueError): m.lire(p)

    def test_paquet_etranger_ou_chemin_traversant_refuse(self):
        for p in ('/tmp/nix/store/'+'a'*32+'-outils', '/nix/store/'+'a'*32+'-outil/../../secret', '', None):
            with self.assertRaises(ValueError): m.paquet(p)

    def test_notice_publique_exacte_et_ouverture_booleenne(self):
        h = charger('vision-inscriptions-https')
        notice = dict(responsable='Jean-Christophe Jameux',contact='RGPD@MrJ.am',
            pays_hebergement='Allemagne',version='vision-20261010',sauvegardes_jours=30,inscriptions_ouvertes=True)
        self.assertTrue(h.verifier_notice(dict(mode='oidc',notice=notice))['inscriptions'])
        for k,v in [('responsable',''),('contact',''),('pays_hebergement','France'),
                    ('version','ancienne'),('sauvegardes_jours',90),('inscriptions_ouvertes',False),
                    ('inscriptions_ouvertes','true'),('inscriptions_ouvertes',1)]:
            with self.subTest(k=k,v=v), self.assertRaises(ValueError):
                h.verifier_notice(dict(mode='oidc',notice={**notice,k:v}))


if __name__ == '__main__': unittest.main()
