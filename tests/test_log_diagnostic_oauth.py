import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

s=importlib.util.spec_from_file_location('diagnostic_oauth',Path(__file__).resolve().parents[1]/'scripts/log-diagnostic.py')
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)

class Inventaire(unittest.TestCase):
    def test_compte_seulement_configurations_sans_ecriture_ni_identifiants(self):
        with tempfile.TemporaryDirectory() as tmp:
            nouveau=Path(tmp)/'new.sqlite';ancien=Path(tmp)/'old.sqlite'
            for p,table,ids in [(nouveau,'log_oauth_clients',['PriveCommun','PriveNeuf']),
                                 (ancien,'oauth_clients',['PriveCommun','PriveAncien'])]:
                with sqlite3.connect(p) as db:
                    db.execute('CREATE TABLE '+table+'(id TEXT)')
                    db.executemany('INSERT INTO '+table+' VALUES(?)',[(x,) for x in ids])
            avant=[p.read_bytes() for p in (nouveau,ancien)]
            out=m.inventaire_clients_mcp(nouveau,ancien)
            self.assertEqual(out,dict(clients_actuels=2,clients_historiques=2,identifiants_communs=1))
            self.assertNotIn('Prive',json.dumps(out))
            self.assertEqual(avant,[p.read_bytes() for p in (nouveau,ancien)])
    def test_registre_absent_ne_cree_pas_de_base(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'absent.sqlite'
            self.assertEqual(m.inventaire_clients_mcp(p,p)['clients_actuels'],0)
            self.assertFalse(p.exists())

if __name__=='__main__':unittest.main()
