"""Attendre seulement la disponibilité, sans rejouer des mutations ou secrets."""
import importlib.util
import io
from pathlib import Path
import unittest
from unittest.mock import patch
import urllib.error
import errno
s=importlib.util.spec_from_file_location('controle',Path(__file__).resolve().parents[1]/'scripts/identite-amorcage-controle.py')
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class Attente(unittest.TestCase):
    def erreur(self,code):return urllib.error.HTTPError('http://loopback-prive',code,'message prive',{},io.BytesIO(b'corps prive'))
    def test_503_puis_disponible_rejoue_uniquement_get_sans_credential(self):
        erreur=self.erreur(503)
        with patch.object(m,'api',side_effect=[erreur,{'issuer':'attendu'}]) as api,patch.object(m.time,'sleep'):
            self.assertEqual(m.attendre_decouverte(object()),dict(issuer='attendu'))
            self.assertTrue(erreur.fp.closed)
            for a in api.call_args_list:
                self.assertEqual(a.args[1],'/realms/mrjam/.well-known/openid-configuration')
                self.assertEqual(set(a.kwargs),{'timeout'});self.assertLessEqual(a.kwargs['timeout'],10)
    def test_codes_et_redirections_etrangers_ne_sont_pas_rejoues(self):
        for code in (302,400,401,403,404,500,502):
            with self.subTest(code=code),patch.object(m,'api',side_effect=self.erreur(code)) as api,patch.object(m.time,'sleep') as pause:
                with self.assertRaises(urllib.error.HTTPError):m.attendre_decouverte(object())
                self.assertEqual(api.call_count,1);pause.assert_not_called()
    def test_connexion_refusee_seule_erreur_reseau_rejouee(self):
        with patch.object(m,'api',side_effect=[urllib.error.URLError(ConnectionRefusedError(errno.ECONNREFUSED,'prive')),{}]),patch.object(m.time,'sleep'):
            self.assertEqual(m.attendre_decouverte(object()),{})
        for e in (urllib.error.URLError(OSError(errno.EACCES,'prive')),ValueError('prive'),TimeoutError('prive')):
            with patch.object(m,'api',side_effect=e) as api,patch.object(m.time,'sleep') as pause:
                with self.assertRaises(type(e)):m.attendre_decouverte(object())
                self.assertEqual(api.call_count,1);pause.assert_not_called()
    def test_limite_monotone_et_timeout_reseau_borne(self):
        with patch.object(m.time,'monotonic',side_effect=[10,10,10.5,11]),patch.object(m.time,'sleep') as pause,patch.object(m,'api',side_effect=self.erreur(503)) as api:
            with self.assertRaisesRegex(ValueError,'Attente d’identité dépassée'):m.attendre_decouverte(object(),maximum=1)
            self.assertEqual(api.call_count,1);self.assertEqual(api.call_args.kwargs,dict(timeout=1));pause.assert_called_once_with(.5)
    def test_sujet_initial_exact_seule_exception_au_refus_de_personne(self):
        sujet='a'*8+'-'+'b'*4+'-'+'c'*4+'-'+'d'*4+'-'+'e'*12
        m.verifier_personnes([]);m.verifier_personnes([{'id':sujet}],sujet)
        for personnes,attendu in (([{'id':sujet}],None),([],sujet),([{'id':'etranger'}],sujet),
                ([{'id':sujet},{'id':'etranger'}],sujet),([{'id':sujet}],'../'+sujet)):
            with self.subTest(personnes=personnes,attendu=attendu),self.assertRaises(ValueError):m.verifier_personnes(personnes,attendu)

if __name__=='__main__':unittest.main()
