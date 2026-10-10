"""Copie complète, AGE natif et refus des archives tronquées ou divergentes."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sqlite3
import subprocess
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def charger(nom):
    s = importlib.util.spec_from_file_location(nom,ROOT/'scripts'/(nom+'.py'))
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


serveur = charger('vision-recuperation')
client = charger('verifier-vision-recuperation')
plan = charger('vision-plan')


class Recuperation(unittest.TestCase):
    def test_confirmation_liee_au_temoin_exact_et_phase_fermee(self):
        confirmation = json.loads((ROOT/'operations/vision-telephone-confirmation.json').read_text())
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/'preuve.json'; p.write_text(json.dumps(confirmation))
            serveur.verifier_confirmation(p)
            for champ,valeur in (('version',True),('cle_publique','autre'),('cle_publique_sha256','a'*64),('execution',1),('dechiffrement_temoin_confirme_par_exploitant',False),('cle_privee_transmise',True)):
                p.write_text(json.dumps(dict(confirmation,**{champ:valeur})))
                with self.assertRaises(ValueError): serveur.verifier_confirmation(p)
        self.assertEqual(plan.verifier(dict(version=1,action='vision-sauvegarder')),'vision-sauvegarder')
        with self.assertRaises(ValueError): plan.verifier(dict(version=1,action='vision-sauvegarder',recipient='tiers'))

    def test_copie_sqlite_avec_wal_et_source_conservee(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)/'sessions.sqlite'; copie = Path(tmp)/'copie.sqlite'
            with sqlite3.connect(source) as f:
                f.execute('PRAGMA journal_mode=WAL'); f.execute('CREATE TABLE sessions(contenu TEXT)')
                f.execute("INSERT INTO sessions VALUES('Synthétique été')"); f.commit(); source.chmod(0o600)
                serveur.copier_sessions(source,copie)
                with sqlite3.connect(copie) as c:
                    self.assertEqual(c.execute('SELECT contenu FROM sessions').fetchall(),[('Synthétique été',)])
                self.assertEqual(f.execute('SELECT count(*) FROM sessions').fetchone(),(1,))
            lien = Path(tmp)/'lien'; lien.symlink_to(source)
            with self.assertRaises(ValueError): serveur.copier_sessions(lien,Path(tmp)/'autre')

    def test_age_reel_copie_integrale_preuve_et_refus_cle_ou_troncature(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); fichiers = {}
            for nom in client.REQUIS:
                p = root/nom; p.write_bytes(('Donnée synthétique '+nom).encode()); p.chmod(0o600); fichiers[nom] = p
            cle = root/'cle.age'
            subprocess.run(['age-keygen','-o',str(cle)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True); cle.chmod(0o600)
            recipient = subprocess.check_output(['age-keygen','-y',str(cle)],stderr=subprocess.DEVNULL,text=True).strip()
            chiffre = root/'copie.age'
            receipt = serveur.archiver(fichiers,chiffre,recipient=recipient)
            resultat = client.verifier(chiffre,cle,receipt['chiffre_sha256'])
            self.assertTrue(resultat['dechiffrement_complet'])
            self.assertFalse(resultat['donnees_en_clair_ecrites'])
            self.assertEqual(hashlib.sha256(resultat['preuve'].encode()).hexdigest(),receipt['preuve_sha256'])
            autre = root/'autre.age'
            subprocess.run(['age-keygen','-o',str(autre)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True); autre.chmod(0o600)
            with self.assertRaises((ValueError,tarfile.TarError,StopIteration)): client.verifier(chiffre,autre,receipt['chiffre_sha256'])
            with self.assertRaises(ValueError): client.verifier(chiffre,cle,'a'*64)
            incomplet = root/'incomplet.age'; incomplet.write_bytes(chiffre.read_bytes()[:-1])
            with self.assertRaises((ValueError,tarfile.TarError,EOFError)): client.verifier(incomplet,cle,serveur.empreinte(incomplet))

    def test_manifeste_archive_chemins_liens_doublons_et_empreintes_refuses(self):
        contenu = b'synthetique'
        fichiers = {n:dict(taille=len(contenu),sha256=hashlib.sha256(contenu).hexdigest()) for n in client.REQUIS}
        manifest = dict(version=1,reference=client.REFERENCE,cle_publique_sha256=client.CLE_SHA256,
            bases_restaurees=True,sqlite_integrite=True,preuve='a'*64,fichiers=fichiers)
        def archive(modif=None,ajout=None,omission=None):
            sortie = io.BytesIO()
            with tarfile.open(fileobj=sortie,mode='w:gz',format=tarfile.USTAR_FORMAT) as t:
                texte = json.dumps(modif or manifest).encode(); info = tarfile.TarInfo('manifest.json'); info.size = len(texte); t.addfile(info,io.BytesIO(texte))
                for nom in sorted(client.REQUIS):
                    if nom == omission: continue
                    info = tarfile.TarInfo(nom); info.size = len(contenu); t.addfile(info,io.BytesIO(contenu))
                if ajout:
                    info = tarfile.TarInfo(ajout); t.addfile(info,io.BytesIO())
            sortie.seek(0); return sortie
        self.assertTrue(client.verifier_archive(archive())['fichiers_identiques_aux_copies_testees'])
        for flux in (archive(ajout='../contenu-prive'),archive(ajout='manifest.json'),archive(ajout='vision.dump'),
                     archive(omission='sessions.sqlite'),archive(modif=dict(manifest,reference='autre')),
                     archive(modif=dict(manifest,fichiers={**fichiers,'vision.dump':dict(taille=len(contenu),sha256='0'*64)}))):
            with self.assertRaises(ValueError): client.verifier_archive(flux)
