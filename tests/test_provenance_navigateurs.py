"""Les reçus décrivent le moteur effectivement lancé, sans caches fictivement requis."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
spec=importlib.util.spec_from_file_location('provenance',ROOT/'scripts/provenance-outils.py')
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)


class Navigateurs(unittest.TestCase):
    def test_pilote_python_node_commun_obligatoire(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);package=root/'state/outils-python/navigateur/lib/python3.12/site-packages/playwright/driver/package'
            package.mkdir(parents=True);(package/'browsers.json').write_text('{"browsers":[]}')
            node=root/'node';node.write_bytes(b'fixture-node')
            autre=root/'node-ancien';autre.write_bytes(b'fixture-autre-version')
            with patch.object(p,'RACINE',root), patch.object(p.shutil,'which',return_value=str(node)):
                with patch.dict(os.environ,{'PLAYWRIGHT_NODEJS_PATH':str(node)},clear=True):
                    self.assertIn('node_driver_commun',p.navigateurs({'navigateurs_python':True},{}))
                for env in ({},{'PLAYWRIGHT_NODEJS_PATH':str(autre)}):
                    with patch.dict(os.environ,env,clear=True), self.assertRaisesRegex(ValueError,'même Node'):
                        p.navigateurs({'navigateurs_python':True},{})

    def test_externe_sans_cache_chromium_et_firefox_conserve(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);pkg=root/'style/node_modules/playwright-core';pkg.mkdir(parents=True)
            (pkg/'browsers.json').write_text(json.dumps({'browsers':[
                {'name':'chromium','revision':'123'}, {'name':'chromium-headless-shell','revision':'123'},
                {'name':'firefox','revision':'456'}]}))
            cache=root/'cache';(cache/'firefox-456').mkdir(parents=True)
            (cache/'firefox-456/firefox').write_bytes(b'fixture-moteur')
            executable=root/'chromium';executable.write_bytes(b'fixture-executable')
            env={'PLAYWRIGHT_BROWSERS_PATH':str(cache),'CHROMIUM':str(executable),
                 'PLAYWRIGHT_CHROMIUM_EXECUTABLE':str(executable),'CHROMIUM_PATH':str(executable)}
            suite={'navigateurs_npm':{'style':'node_modules'},'navigateurs':['chromium','chromium-headless-shell','firefox'],'chromium_externe':True}
            with patch.dict(os.environ,env):
                result=p.navigateurs(suite,{'style':root/'style'})
                self.assertIn('style/firefox-456',result)
                self.assertIn('chromium_externe',result)
                self.assertFalse(any('/chromium-' in k for k in result))
                autre=root/'autre';autre.write_bytes(b'autre')
                with patch.dict(os.environ,{'CHROMIUM_PATH':str(autre)}):
                    with self.assertRaises(ValueError):p.navigateurs(suite,{'style':root/'style'})
                with patch.dict(os.environ,{'CHROMIUM_PATH':''}):
                    with self.assertRaises(ValueError):p.navigateurs(suite,{'style':root/'style'})
                suite['chromium_externe']=False
                with self.assertRaises(ValueError):p.navigateurs(suite,{'style':root/'style'})

    def test_cache_firefox_absent_refuse_meme_avec_chromium_externe(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);pkg=root/'node_modules/playwright-core';pkg.mkdir(parents=True)
            (pkg/'browsers.json').write_text(json.dumps({'browsers':[{'name':'firefox','revision':'456'}]}))
            with patch.dict(os.environ,{'PLAYWRIGHT_BROWSERS_PATH':str(root/'absent')}):
                with self.assertRaises(ValueError):p.navigateurs({'navigateurs_npm':{'style':'node_modules'},'navigateurs':['firefox'],'chromium_externe':True},{'style':root})
