import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
spec=importlib.util.spec_from_file_location('ressources',ROOT/'scripts/revoir-ressources.py')
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)


class Amorçage(unittest.TestCase):
    def test_bootstrap_minimal_accepte(self):
        parser=r.Bootstrap();parser.feed('<html><head><title>Titre</title></head><body><div id="app"></div><noscript>JavaScript requis</noscript></body></html>')
        self.assertEqual([],parser.errors)

    def test_presentation_html_ou_css_refusee(self):
        for content in ['<p>Vue</p>','<div id="app" style="color:red"></div>','<style>body{color:red}</style>','<div id="app">Vue</div>','<div id="app"></div><div id="autre"></div>']:
            with self.subTest(content=content):
                parser=r.Bootstrap();parser.feed('<body>'+content+'</body>')
                self.assertTrue(parser.errors)


class Javascript(unittest.TestCase):
    def test_ast_symboles_et_commentaires(self):
        cases=[('initialisation','Elm.Main.init({node:document.getElementById("app")});',False),
               ('commentaire','// el.style.color = "red"\nconst x="innerHTML";',False),
               ('style','el.style.color="red";',True),
               ('calculé','el["style"].color="red";',True),
               ('optionnel','const css=el?.style; css.color="red";',True),
               ('alias','const css=el.style; css.color="red";',True),
               ('constructeur','const construire=document.createElement; construire("div");',True),
               ('css','import "./vue.css";',True),
               ('animation','el.animate([{opacity:0},{opacity:1}],200);',True)]
        lock=json.loads((ROOT/'assemblage/elm-review/outils.lock.json').read_text())['parseur_js_existant']
        parser=ROOT.parent/'M-moire'/lock['fichier']
        p=subprocess.run(['node',str(ROOT/'scripts/revoir-interop.cjs'),str(parser)],
                         input=json.dumps([{'path':name,'content':code,'exceptions':[]} for name,code,_ in cases]),
                         capture_output=True,text=True)
        self.assertEqual(1,p.returncode,p.stderr[-1000:])
        errors=json.loads(p.stdout);names={e['fichier'] for e in errors}
        for name,_,fail in cases:
            with self.subTest(name=name):self.assertEqual(fail,name in names)
        self.assertFalse(any('erreur' in e for e in errors),'Une erreur de parsing ne prouve pas le rejet attendu')
