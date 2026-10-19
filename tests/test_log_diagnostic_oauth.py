import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

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

    def test_etapes_reconnexion_expiration_et_rejeu_sans_lire_les_secrets(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'log.sqlite'
            with sqlite3.connect(p) as db:
                db.executescript('''
                    CREATE TABLE log_sessions(digest TEXT,host TEXT,expires INTEGER,seen INTEGER,access TEXT,refresh TEXT);
                    CREATE TABLE log_oauth_requests(session TEXT,expires INTEGER);
                    CREATE TABLE log_oauth_codes(session TEXT,expires INTEGER);
                    CREATE TABLE log_oauth_tokens(session TEXT,kind TEXT,expires INTEGER,revoked INTEGER);
                    INSERT INTO log_sessions VALUES('session-privee','vision.mrj.am',2000,901,'secret-acces','secret-refresh');
                    INSERT INTO log_sessions VALUES('expiree','vision.mrj.am',999,800,'secret-acces','secret-refresh');
                    INSERT INTO log_oauth_requests VALUES('session-privee',1100);
                    INSERT INTO log_oauth_codes VALUES('session-privee',1100),('expiree',900),('absente',1100);
                    INSERT INTO log_oauth_tokens VALUES('session-privee','access',1100,NULL),
                        ('session-privee','access',900,NULL),('session-privee','refresh',2000,950),
                        ('session-privee','refresh',2000,NULL),('absente','refresh',2000,NULL);
                ''')
            avant=p.read_bytes()
            connexion=sqlite3.connect
            def lecture(*args,**kwargs):
                db=connexion(*args,**kwargs)
                db.set_authorizer(lambda action,table,col,*reste: sqlite3.SQLITE_DENY
                    if action==sqlite3.SQLITE_READ and col in ('access','refresh') else sqlite3.SQLITE_OK)
                return db
            with patch.object(m.sqlite3,'connect',side_effect=lecture):
                out=m.inventaire_reconnexion_mcp(p,1000)
            self.assertEqual(out['sessions']['vision.mrj.am'],
                {'total':2,'non_expirees':1,'derniere_lecture_minute':15})
            self.assertEqual(out['codes'],{'total':3,'non_expires':2,
                'session_absente_ou_expiree':2,'derniere_expiration_minute':18})
            self.assertEqual(out['jetons'][0]['non_expires_non_revoques'],1)
            self.assertEqual(out['jetons'][1]['revoques'],1)
            self.assertEqual(out['jetons'][1]['session_absente_ou_expiree'],1)
            self.assertNotIn('secret',json.dumps(out));self.assertNotIn('privee',json.dumps(out))
            self.assertEqual(avant,p.read_bytes())

    def test_reconnexion_absente_et_schema_incomplet(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'log.sqlite'
            self.assertEqual(m.inventaire_reconnexion_mcp(p,1000),{'present':False})
            self.assertFalse(p.exists())
            with sqlite3.connect(p) as db:db.execute('CREATE TABLE autre(n INTEGER)')
            self.assertEqual(m.inventaire_reconnexion_mcp(p,1000),{'present':True,'schema_complet':False})

if __name__=='__main__':unittest.main()
