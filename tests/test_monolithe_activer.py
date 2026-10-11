"""Retour du code avec derniers états, refus et reprise ; aucun VPS contacté."""
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('activer_monolithe',ROOT/'scripts/monolithe-activer.py')
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)


class Retour(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.r=Path(self.tmp.name)
        self.d=self.r/('a'*40);self.d.mkdir(mode=0o700)
        self.current=self.r/'commun';self.current.mkdir(mode=0o700)
        self.old=self.r/'historique';self.old.mkdir(mode=0o700)
        self.source=self.current/'courriel/file.sqlite';self.source.parent.mkdir(mode=0o700)
        self.target=self.old/'file.sqlite'
        for p,rows in [(self.source,[(1,b'\x00\xff',0),(2,b'apres-bascule',None)]),(self.target,[(1,b'ancien',0)])]:
            with sqlite3.connect(p) as c:
                c.execute('CREATE TABLE courriels(id int PRIMARY KEY,message BLOB,accepte int)')
                c.executemany('INSERT INTO courriels VALUES(?,?,?)',rows)
            p.chmod(0o600)
        self.plan={'phase':'service-demarre','etats':{'courriel':m.proprietes(self.target)},'unites_avant':{'vision':'active','matheval':'active'}}
        self.before={'generation':'/nix/store/ancien','configuration_cible':'/config-original',
                     'configuration_lien':'/config-original'}
        self.prepare={'avant':self.before};self.appels=[]

    def lancer(self):
        with patch.object(m,'ETAT_METIER',self.current),patch.object(m,'PORTE',self.r/'porte'),\
             patch.object(m.stage,'ETATS',{'courriel':str(self.target)}),\
             patch.object(m.stage,'commande',side_effect=lambda a,d:self.appels.append([str(v) for v in a]) or b''),\
             patch.object(m.stage,'etat',return_value=self.before),patch.object(m,'changer_configuration'):
            m.retour(self.d,self.prepare,self.plan)

    def test_retour_conserve_ecritures_posterieures_et_ne_restaure_pas_sql(self):
        self.lancer()
        with sqlite3.connect(self.target) as c:
            self.assertEqual(c.execute('SELECT * FROM courriels ORDER BY id').fetchall(),[(1,b'\x00\xff',0),(2,b'apres-bascule',None)])
        self.assertFalse(any('pg_restore' in ' '.join(a) or 'pg_dump' in ' '.join(a) for a in self.appels))
        self.assertTrue(json.loads((self.d/'retour.json').read_text())['derniers_etats_durables_recopies'])

    def test_reprise_retour_necrase_pas_une_ecriture_historique_recente(self):
        self.lancer()
        with sqlite3.connect(self.target) as c:c.execute("INSERT INTO courriels VALUES(3,X'01',1)")
        self.lancer()
        with sqlite3.connect(self.target) as c:self.assertEqual(c.execute('SELECT count(*) FROM courriels').fetchone(),(3,))

    def test_cible_redirigee_et_copie_concurrente_refusees(self):
        self.target.unlink();self.target.symlink_to(self.source)
        with self.assertRaisesRegex(ValueError,'redirigée'):self.lancer()
        self.assertFalse((self.d/'retour.json').exists())
        self.target.unlink();self.target.with_name(self.target.name+'.assemblage-copie').write_text('concurrent')
        with self.assertRaisesRegex(ValueError,'concurrente'):self.lancer()

    def test_avant_transfert_ne_reinjecte_pas_d_etat(self):
        self.plan['phase']='anciens-arretes';self.lancer()
        with sqlite3.connect(self.target) as c:self.assertEqual(c.execute('SELECT message FROM courriels').fetchone(),(b'ancien',))

    def test_retour_reste_utilisable_apres_validation(self):
        (self.d/'termine.json').write_text('{"validation":true}')
        self.lancer();self.assertTrue((self.d/'retour.json').exists());self.assertTrue((self.d/'termine.json').exists())


if __name__=='__main__':unittest.main()
