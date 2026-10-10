"""Refuser les artefacts altérés et l'authentification par en-tête client."""
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('activation_https',ROOT/'scripts/vision-essai-https.py')
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)


class Https(unittest.TestCase):
    def setUp(self):
        self.body=b'artefact exact'
        self.manifeste={'fichiers':{n:hashlib.sha256(self.body).hexdigest() for n in
            ['index.html','app.html','privacy.html',*[f'assets/{i}' for i in range(19)]]}}
    def repondre(self,opener,origine,route,**options):
        if route=='/interface-manifest.json':return 200,{},json.dumps(self.manifeste).encode()
        if route.startswith(('/api/','/auth/')) or route=='/mcp':return 401,{},b'{}'
        return 200,{},self.body
    def test_refus_anonyme_et_identite_falsifiee_verifies(self):
        with patch.object(m.h,'demander',side_effect=self.repondre),patch.object(m.h,'verifier'):
            self.assertEqual(m.verifier(None,self.manifeste)['fichiers_interface'],22)
    def test_artefact_modifie_et_header_admin_accepte_refuses(self):
        for variante in ('contenu','administrateur'):
            def repondre(*a,**k):
                if variante=='contenu' and a[2]=='/assets/0':return 200,{},b'altere'
                if variante=='administrateur' and k.get('headers',{}).get('X-Vision-Administration'):
                    return 200,{},b'{}'
                return self.repondre(*a,**k)
            with self.subTest(variante=variante),patch.object(m.h,'demander',side_effect=repondre),patch.object(m.h,'verifier'):
                with self.assertRaises(ValueError):m.verifier(None,self.manifeste)

    def test_projection_exacte_sans_corps_ni_cookies(self):
        def repondre(*a,**k):
            if a[2]=='/assets/0':return 200,{},b'contenu prive qui ne doit pas sortir'
            return self.repondre(*a,**k)
        with patch.object(m.h,'demander',side_effect=repondre),self.assertRaises(m.RefusPublic) as erreur:
            m.verifier(None,self.manifeste)
        self.assertEqual(erreur.exception.projection,dict(controle_https_refuse=True,
            phase='artefact',route='/assets/0',statut=200,raison='empreinte_differente'))

    def test_cookie_reel_et_historique_falsifies(self):
        cookies=[]
        def repondre(*a,**k):
            if k.get('headers',{}).get('Cookie'):cookies.append(k['headers']['Cookie'])
            return self.repondre(*a,**k)
        with patch.object(m.h,'demander',side_effect=repondre),patch.object(m.h,'verifier'):
            m.verifier(None,self.manifeste)
        self.assertTrue(cookies)
        self.assertTrue(all('__Host-mrj_session=invalide' in c and '__Secure-mrj_session=invalide' in c for c in cookies))


if __name__=='__main__':unittest.main()
