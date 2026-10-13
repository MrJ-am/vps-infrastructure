import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from types import SimpleNamespace

s=importlib.util.spec_from_file_location('clients_mcp',Path(__file__).resolve().parents[1]/'scripts/log-clients-mcp.py')
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)

class Reprise(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.old=Path(self.tmp.name)/'old.sqlite';self.new=Path(self.tmp.name)/'new.sqlite'
        self.row=('A'*32,'ChatGPT',json.dumps(['https://chatgpt.com/connector_platform/oauth/callback']),100)
        legacy=importlib.util.spec_from_file_location('oauth_reference',Path(__file__).resolve().parents[1]/'services/mrj-auth/oauth.py')
        reference=importlib.util.module_from_spec(legacy);legacy.loader.exec_module(reference)
        reference.initialiser(SimpleNamespace(connect=lambda:sqlite3.connect(self.old)))
        with sqlite3.connect(self.old) as db:
            db.execute('INSERT INTO oauth_clients VALUES(?,?,?,?)',self.row)
            db.execute('CREATE TABLE sessions(secret TEXT)');db.execute("INSERT INTO sessions VALUES('synthetique-prive')")
        with sqlite3.connect(self.new) as db:
            db.execute('CREATE TABLE log_oauth_clients(id TEXT PRIMARY KEY,name TEXT,redirects TEXT,created INTEGER)')
            db.execute('CREATE TABLE log_sessions(secret TEXT)');db.execute("INSERT INTO log_sessions VALUES('session-conservee')")
    def test_reprise_idempotente_sans_session_ni_token(self):
        avant=self.old.read_bytes();clients=m.lire_clients(self.old)
        self.assertEqual(m.reprendre(clients,self.new)['clients_importes'],1)
        self.assertEqual(m.reprendre(clients,self.new)['clients_identiques_conserves'],1)
        with sqlite3.connect(self.new) as db:
            self.assertEqual(db.execute('SELECT * FROM log_oauth_clients').fetchone(),self.row)
            self.assertEqual(db.execute('SELECT * FROM log_sessions').fetchall(),[('session-conservee',)])
            self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='sessions'").fetchone())
        self.assertEqual(self.old.read_bytes(),avant)
    def test_conflit_annule_aussi_les_insertions_precedentes(self):
        with sqlite3.connect(self.new) as db:db.execute('INSERT INTO log_oauth_clients VALUES(?,?,?,?)',('B'*32,'Autre',self.row[2],101))
        clients=[self.row,('B'*32,'Different',self.row[2],101)]
        with self.assertRaises(ValueError):m.reprendre(clients,self.new)
        with sqlite3.connect(self.new) as db:self.assertEqual(db.execute('SELECT id FROM log_oauth_clients').fetchall(),[('B'*32,)])
    def test_retour_non_https_ou_credential_refuse_avant_ecriture(self):
        for uri in ['http://example.test/return','https://identifiant:secret@example.test/callback','https://example.test/#frag']:
            with sqlite3.connect(self.old) as db:db.execute('UPDATE oauth_clients SET redirections=?',(json.dumps([uri]),))
            with self.subTest(uri=uri),self.assertRaises(ValueError):m.lire_clients(self.old)

if __name__=='__main__':unittest.main()
