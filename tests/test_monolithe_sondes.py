"""Vraies réponses HTTP locales ; aucune application ou donnée de production."""
from collections import deque
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import importlib.util
import json
from pathlib import Path
import threading
import time
import tempfile
import unittest
from unittest.mock import patch

s=importlib.util.spec_from_file_location('reference_sondes',Path(__file__).resolve().parents[1]/'scripts/monolithe-reference.py')
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)


@contextmanager
def serveur(codes):
    reponses=deque(codes);instants=[]
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            instants.append(time.monotonic())
            code=reponses.popleft() if reponses else 200
            self.send_response(code);self.end_headers();self.wfile.write(b'public')
        def log_message(self,*args):pass
    http=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
    try:yield 'http://127.0.0.1:'+str(http.server_port),instants
    finally:http.shutdown();http.server_close();thread.join()


class Sondes(unittest.TestCase):
    def test_formats_comptes_agreges_sans_secret_ni_identite(self):
        with tempfile.TemporaryDirectory() as tmp:
            fichier=Path(tmp)/'htpasswd'
            secret='$6$rounds=656000$selSynthese$'+'a'*86
            fichier.write_text('alice:'+secret+'\nbob:$argon2id$synthetique\nvision-bootstrap-test:'+secret+'\nvision-disabled-test:'+secret+'\n')
            resultat=m.comptes_vision_historique(fichier)
        self.assertEqual(resultat,{'present':True,'comptes_eligibles':2,'sha512_crypt':1,
                                  'formats_non_reconnus':1,'doublons':0,'lignes_invalides':0})
        sortie=json.dumps(resultat)
        for sensible in ('alice','bob',secret,'selSynthese','argon2'):
            self.assertNotIn(sensible,sortie)

    def test_comptes_absents_doublons_et_fichier_invalide(self):
        with tempfile.TemporaryDirectory() as tmp:
            fichier=Path(tmp)/'htpasswd'
            self.assertEqual(m.comptes_vision_historique(fichier),{'present':False})
            fichier.write_text('alice:$6$malforme\nalice:$6$sel$'+'a'*86+'\nligne-invalide\n')
            r=m.comptes_vision_historique(fichier)
            self.assertEqual((r['comptes_eligibles'],r['sha512_crypt'],r['doublons'],r['lignes_invalides']),(1,1,1,1))
            fichier.write_text('SECRET'*12000)
            with self.assertRaisesRegex(ValueError,'hors borne') as e:m.comptes_vision_historique(fichier)
            self.assertNotIn('SECRET',str(e.exception))

    def test_disponibilite_distincte_des_dix_mesures_espacement_reel(self):
        with serveur([503,200]+[200]*10) as (url,instants):
            r=m.latence(url,(200,),attendre=True)
        self.assertEqual(r['disponibilite_codes'],[503,200])
        self.assertEqual(r['codes'],[200]);self.assertEqual(r['n'],10)
        self.assertEqual(len(instants),12)
        self.assertTrue(all(b-a>=.24 for a,b in zip(instants[1:],instants[2:])))
        # Le temps d'attente d'une seconde et les pauses ne sont pas des
        # latences d'un serveur qui répond immédiatement.
        self.assertLess(r['mediane_ms'],250)

    def test_429_mesuree_reste_un_echec_avec_codes_sans_corps(self):
        with serveur([200]*9+[429]) as (url,instants):
            with self.assertRaises(m.SondeHorsContrat) as erreur:m.latence(url,(200,))
        self.assertEqual(erreur.exception.codes,[200,429]);self.assertEqual(len(instants),10)
        self.assertNotIn('public',str(erreur.exception));self.assertNotIn(url,str(erreur.exception))

    def test_statut_permanent_refuse_sans_reessai(self):
        for code in (403,404,500):
            with self.subTest(code=code),serveur([code]) as (url,instants):
                with self.assertRaises(m.SondeHorsContrat) as erreur:m.latence(url,(200,),attendre=True)
                self.assertEqual(erreur.exception.codes,[code]);self.assertEqual(len(instants),1)

    def test_indisponibilite_persistante_bornee(self):
        # Horloge simulée seulement dans ce test de deadline : time est un
        # module partagé et sa substitution touchait aussi le thread HTTP.
        with patch.object(m,'lecture_http',return_value=(503,0)) as lire,\
             patch.object(m.time,'monotonic',side_effect=[0,46]):
            with self.assertRaises(m.SondeHorsContrat) as erreur:m.latence('http://fixture',(200,),attendre=True)
            self.assertEqual(erreur.exception.codes,[503]);lire.assert_called_once_with('http://fixture')


if __name__=='__main__':unittest.main()
