"""Jetons OIDC signés, anti-rejeu, cookies par hôte, MFA et droits vivants."""
from contextlib import closing
import importlib
import json
from pathlib import Path
import secrets
import sqlite3
import sys
import tempfile
import time
import unittest
from unittest.mock import patch,Mock
from urllib.parse import parse_qs,urlsplit

from authlib.jose import JsonWebKey,JsonWebToken
from authlib.jose.errors import JoseError

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'services/mrj-auth'))
oidc=importlib.import_module('oidc')

class Registre:
    actif=True
    admin=True
    def appeler(self,f,*args):
        if f=='notice':return {'inscriptions_ouvertes':False}
        return {'utilisateur':'alice','administrateur':self.admin,'actif':self.actif}

class OIDC(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name);(root/'credentials').write_text('fixture-sans-mot-de-passe\n');(root/'secret').write_text(secrets.token_urlsafe(32))
        self.registre=Registre()
        self.app=oidc.SessionsOIDC(root/'sessions.sqlite',root/'credentials','mrj.am',['vision.mrj.am','notes.mrj.am'],
          'https://compte.mrj.am/realms/mrjam','http://127.0.0.1:8085/realms/mrjam','mrjam-vision',root/'secret',self.registre)
        self.cle=JsonWebKey.generate_key('RSA',2048,is_private=True,options={'kid':'test-local'})

    def callback(self,extra=None):
        url,binding=self.app.demarrer('vision.mrj.am',stepup=True)
        q=parse_qs(urlsplit(url).query);state=q['state'][0]
        self.assertEqual(q['code_challenge_method'],['S256']);self.assertEqual(q['prompt'],['login'])
        with closing(self.app.connect()) as db:
            row=db.execute('SELECT * FROM oidc_transactions WHERE state=?',(oidc.digest(state),)).fetchone()
        self.assertNotEqual(row['binding'],binding)
        now=int(time.time())
        claims={'iss':self.app.issuer,'aud':'mrjam-vision','sub':'id-commun-stable','iat':now,'exp':now+300,
                'auth_time':now,'nonce':q['nonce'][0],'amr':['pwd','otp'],**(extra or {})}
        token=JsonWebToken(['RS256']).encode({'alg':'RS256','kid':'test-local'},claims,self.cle).decode()
        client=Mock();client.fetch_token.return_value={'id_token':token,'access_token':'test-local'}
        response=Mock();response.json.return_value={'keys':[self.cle.as_dict(is_private=False)]}
        with patch.object(self.app,'client',return_value=client),patch.object(oidc.requests,'get',return_value=response):
            result=self.app.terminer('vision.mrj.am',state,'code-test',oidc.STATE_COOKIE+'='+binding)
        client.fetch_token.assert_called_once()
        self.assertEqual(client.fetch_token.call_args.kwargs['code_verifier'],row['verifier'])
        return result,state,binding

    def test_cookie_mfa_host_and_role_revocation(self):
        (token,_),_,_=self.callback()
        cookie=self.app.cookie(token)
        self.assertNotIn('Domain=',cookie);self.assertIn('__Host-',cookie)
        self.assertTrue(self.app.session(cookie,'vision.mrj.am')['mfa'])
        self.assertIsNone(self.app.session(cookie,'notes.mrj.am'))
        self.registre.admin=False
        self.assertFalse(self.app.session(cookie,'vision.mrj.am')['compte']['administrateur'])
        self.registre.actif=False
        self.assertIsNone(self.app.session(cookie,'vision.mrj.am'))

    def test_fresh_otp_required(self):
        for extra in ({'amr':['pwd']},{'auth_time':int(time.time())-301}, {'amr':['otp']}):
            (token,_),_,_=self.callback(extra)
            self.assertFalse(self.app.session(self.app.cookie(token),'vision.mrj.am')['mfa'])

    def test_signed_claims_checked_before_identity(self):
        for extra in ({'iss':'https://evil.example.test'},{'aud':'autre-outil'}, {'nonce':'substitution'},
                      {'exp':int(time.time())-60}):
            with self.assertRaises(JoseError):self.callback(extra)

    def test_replay_and_external_return_rejected(self):
        _,state,binding=self.callback()
        with self.assertRaisesRegex(ValueError,'etat_invalide'):
            self.app.terminer('vision.mrj.am',state,'code-test',oidc.STATE_COOKIE+'='+binding)
        for retour in ('https://evil.test','//evil.test','/oauth/authorize?x=\nLocation:evil'):
            with self.assertRaises(ValueError):self.app.demarrer('vision.mrj.am',retour)
        url,binding=self.app.demarrer('vision.mrj.am');state=parse_qs(urlsplit(url).query)['state'][0]
        with self.assertRaisesRegex(ValueError,'etat_invalide'):
            self.app.terminer('vision.mrj.am',state,'code-test',oidc.STATE_COOKIE+'='+secrets.token_urlsafe(32))

    def logout_token(self,extra=None):
        claims={'iss':self.app.issuer,'aud':self.app.client_id,'iat':int(time.time()),'jti':secrets.token_hex(16),
          'sub':'id-commun-stable','events':{'http://schemas.openid.net/event/backchannel-logout':{}},**(extra or {})}
        return JsonWebToken(['RS256']).encode({'alg':'RS256','kid':'test-local'},claims,self.cle).decode()

    def test_backchannel_signee_revoque_et_refuse_rejeu(self):
        (secret,_),_,_=self.callback()
        response=Mock();response.json.return_value={'keys':[self.cle.as_dict(is_private=False)]}
        token=self.logout_token()
        with patch.object(oidc.requests,'get',return_value=response):
            self.app.deconnexion_commune(token)
            self.assertIsNone(self.app.session(self.app.cookie(secret),'vision.mrj.am'))
            with self.assertRaises(sqlite3.IntegrityError):self.app.deconnexion_commune(token)

    def test_backchannel_invalide_ne_revoque_pas(self):
        (secret,_),_,_=self.callback()
        response=Mock();response.json.return_value={'keys':[self.cle.as_dict(is_private=False)]}
        with patch.object(oidc.requests,'get',return_value=response):
            for extra in ({'iss':'https://evil.test'},{'aud':'autre-outil'},{'nonce':'interdit'},
                          {'iat':int(time.time())-121},{'events':{}},{'sub':''}):
                with self.assertRaises((JoseError,ValueError)):self.app.deconnexion_commune(self.logout_token(extra))
        self.assertIsNotNone(self.app.session(self.app.cookie(secret),'vision.mrj.am'))

if __name__=='__main__':unittest.main()
