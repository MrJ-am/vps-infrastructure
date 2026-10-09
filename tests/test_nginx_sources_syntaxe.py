"""Le parseur Nginx vérifie les directives réelles des trois téléchargements."""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]


class Syntaxe(unittest.TestCase):
    @unittest.skipUnless(shutil.which('nginx'),'Nginx requis dans la qualification complète et la CI')
    def test_blocs_reels_et_regression_point_virgule(self):
        blocs=[]
        for nom in ('identite-amorcage.nix','vision-gestion.nix'):
            source=(ROOT/'modules'/nom).read_text()
            blocs+=re.findall(r'"= /code-source/[^"\n]+"\s*=\s*\{.*?extraConfig\s*=\s*\'\'(.*?)\'\';',source,re.S)
        self.assertEqual(len(blocs),3)
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp);(d/'logs').mkdir()
            def tester(bloc):
                p=d/'nginx.conf'
                p.write_text('error_log stderr;\npid '+str(d/'nginx.pid')+';\nevents {}\nhttp { server { listen 127.0.0.1:8089; location / { alias '+str(d)+'/;\n'+bloc+'\n} } }\n')
                return subprocess.run(['nginx','-t','-p',str(d)+'/', '-c',str(p)],capture_output=True,timeout=10)
            for bloc in blocs:
                r=tester(bloc);self.assertEqual(r.returncode,0,r.stderr.decode())
            r=tester(blocs[0].replace('types {}','types {};'))
            self.assertNotEqual(r.returncode,0);self.assertIn(b'unexpected',r.stderr)
