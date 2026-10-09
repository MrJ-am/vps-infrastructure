"""Une notation mappée conserve exactement la même adresse IPv4 et le même port."""
import importlib.util
from pathlib import Path
import unittest
s=importlib.util.spec_from_file_location('boucle',Path(__file__).resolve().parents[1]/'scripts/vision-identite-boucle-locale.py')
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class Boucle(unittest.TestCase):
    @staticmethod
    def ligne(ip):return 'LISTEN 0 4096 '+ip+' *:* users:(("java",pid=123,fd=1))\n'
    def test_ipv4_et_uniquement_son_equivalent_mappe(self):
        for ip in ('127.0.0.1:8085','[::ffff:127.0.0.1]:8085','[::ffff:7f00:1]:8085'):
            with self.subTest(ip=ip):self.assertTrue(m.verifier(self.ligne(ip)))
    def test_exposition_ou_adresse_autre_refusee(self):
        for ip in ('0.0.0.0:8085','*:8085','[::]:8085','[::1]:8085','127.0.0.2:8085',
                '[::ffff:127.0.0.2]:8085','[::ffff:187.77.95.158]:8085', '187.77.95.158:8085',
                '127.0.0.1:8086','[::ffff:127.0.0.1%eth0]:8085','[::ffff:127.0.0.1]:08085'):
            with self.subTest(ip=ip):self.assertFalse(m.verifier(self.ligne(ip)))
    def test_ecoute_unique_et_format_valide_requis(self):
        for valeur in ('',self.ligne('127.0.0.1:8085')+self.ligne('[::]:8085'),
                self.ligne('127.0.0.1:8085')+'\n',self.ligne('127.0.0.1:8085').replace('LISTEN','ESTAB'),
                'LISTEN 0',self.ligne('[invalide]:8085')):
            with self.subTest(valeur=valeur):self.assertFalse(m.verifier(valeur))
if __name__=='__main__':unittest.main()
