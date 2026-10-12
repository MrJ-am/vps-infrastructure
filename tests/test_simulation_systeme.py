import importlib.util
from pathlib import Path
import unittest

s=importlib.util.spec_from_file_location('simulation',Path(__file__).resolve().parents[1]/'scripts/simulation-systeme.py')
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)


class Simulation(unittest.TestCase):
    def test_format_reel_would_ne_contourne_pas_la_protection(self):
        for texte in ('would stop','would restart','stopping','restarting'):
            with self.subTest(texte=texte),self.assertRaisesRegex(ValueError,'service préservé'):
                m.verifier('would activate the configuration\n'+texte+' the following units: nginx.service, postgresql.service\n',['postgresql.service'])

    def test_reload_autorise_et_noms_entiers(self):
        r=m.verifier('would activate the configuration\nwould reload the following units: postgresql.service, nginx.service\nwould restart the following units: faux-postgresql.service\n',['postgresql.service'])
        self.assertEqual(r['reload'],{'postgresql.service','nginx.service'})
        self.assertEqual(r['restart'],{'faux-postgresql.service'})

    def test_format_absent_et_interruption_socle_refuses(self):
        for t in ('aucune simulation','would activate the configuration\nwould restart systemd','would activate the configuration\nwould stop swap'):
            with self.subTest(t=t),self.assertRaises(ValueError):m.verifier(t,[])


if __name__=='__main__':unittest.main()
