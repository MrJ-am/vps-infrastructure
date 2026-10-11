import importlib.util
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

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
    def test_delegation_limitee_aux_balises_natives(self):
        exception=[{'fonction':'telecharger','capacite':'presentation-dom','operation':'createElement','balises':['a']}]
        cases=[('lien','function telecharger(){document.createElement("a");}',False),
               ('calcule','function telecharger(){document["createElement"]("a");}',False),
               ('vue','function telecharger(){document.createElement("div");}',True),
               ('autre','function autre(){document.createElement("a");}',True),
               ('dynamique','function telecharger(tag){document.createElement(tag);}',True),
               ('alias','function telecharger(){const creer=document.createElement;creer("a");}',True),
               ('style','function telecharger(){document.createElement("a");el.style.color="red";}',True),
               ('html','function telecharger(){el.innerHTML="<p>Vue</p>";}',True),
               ('animation','function telecharger(){requestAnimationFrame(actualiser);}',True)]
        lock=json.loads((ROOT/'assemblage/elm-review/outils.lock.json').read_text())['parseur_js_existant']
        result=subprocess.run(['node',str(ROOT/'scripts/revoir-interop.cjs'),str(ROOT.parent/'M-moire'/lock['fichier'])],
                              input=json.dumps([{'path':name,'content':code,'exceptions':exception} for name,code,_ in cases]),
                              capture_output=True,text=True)
        self.assertEqual(1,result.returncode,result.stderr[-1000:])
        errors=json.loads(result.stdout);names={e['fichier'] for e in errors}
        self.assertFalse(any('erreur' in e for e in errors))
        for name,_,fail in cases:
            with self.subTest(name=name):self.assertEqual(fail,name in names)

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


class SourcesReellementAssemblees(unittest.TestCase):
    def test_export_genere_exige_la_meme_provenance(self):
        with tempfile.TemporaryDirectory(prefix='export-fixture-',dir=ROOT/'state') as temporary:
            infrastructure=Path(temporary);config=infrastructure/'assemblage/elm-review';config.mkdir(parents=True)
            style=infrastructure/'style';(style/'public').mkdir(parents=True)
            subprocess.run(['git','init','--quiet',str(style)],check=True)
            css=style/'public/palette.css';css.write_text(':root{--couleur:#123456}')
            producteur=style/'producteur.elm';producteur.write_text('module Producteur exposing (valeur)\nvaleur = 1')
            empreinte=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
            declaration={'sha256':empreinte(css),'producteurs':{'producteur.elm':empreinte(producteur)}}
            (config/'ressources.json').write_text(json.dumps({'racines':{'style':['public/']},'bibliotheques_generees':{'style/public/palette.css':declaration},'adaptateurs_js':{}}))
            (config/'outils.lock.json').write_bytes((ROOT/'assemblage/elm-review/outils.lock.json').read_bytes())
            (infrastructure/'scripts').symlink_to(ROOT/'scripts',target_is_directory=True)
            sources={'style':style,'matheval':ROOT.parent/'M-moire'}
            with patch.object(r,'RACINE',infrastructure):
                r.verifier('style',sources)
                producteur.write_text('module Producteur exposing (valeur)\nvaleur = 2')
                with self.assertRaisesRegex(ValueError,'1 violations'):r.verifier('style',sources)
                rapport=json.loads((infrastructure/'state/review-frontends/style-ressources.json').read_text())
                self.assertIn('producteur différent',rapport['erreurs'][0]['erreur'])
                css.write_text('body{color:red}')
                with self.assertRaisesRegex(ValueError,'2 violations'):r.verifier('style',sources)

    def test_nouveaux_fichiers_retraits_et_liens(self):
        with tempfile.TemporaryDirectory(prefix='ressources-fixture-',dir=ROOT/'state') as temporary:
            infrastructure=Path(temporary);config=infrastructure/'assemblage/elm-review';config.mkdir(parents=True)
            (config/'ressources.json').write_text(json.dumps({'racines':{'style':['public/']},'bibliotheques_generees':{},'adaptateurs_js':{}}))
            (config/'outils.lock.json').write_bytes((ROOT/'assemblage/elm-review/outils.lock.json').read_bytes())
            # Le vérificateur utilise le même parseur existant, sans installer d'outil.
            (infrastructure/'scripts').symlink_to(ROOT/'scripts',target_is_directory=True)
            style=infrastructure/'style';(style/'public').mkdir(parents=True)
            subprocess.run(['git','init','--quiet',str(style)],check=True)
            css=style/'public/nouveau.css';css.write_text('body{color:red}')
            sources={'style':style,'matheval':ROOT.parent/'M-moire'}
            with patch.object(r,'RACINE',infrastructure):
                with self.assertRaisesRegex(ValueError,'1 violations'):r.verifier('style',sources)
                rapport=json.loads((infrastructure/'state/review-frontends/style-ressources.json').read_text())
                self.assertEqual('style/public/nouveau.css',rapport['erreurs'][0]['fichier'])
                subprocess.run(['git','add','public/nouveau.css'],cwd=style,check=True)
                css.unlink()
                r.verifier('style',sources)
                lien=style/'public/source.css';lien.symlink_to(css)
                with self.assertRaisesRegex(ValueError,'liée symboliquement'):r.verifier('style',sources)
