"""Transport chiffré verrouillé : refus avant tout accès réseau."""
import ast
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
s=importlib.util.spec_from_file_location('transport_monolithe',ROOT/'scripts/monolithe-stage.py')
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)


class Transport(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        (self.root/'operations').mkdir();(self.root/'scripts').mkdir()
        (self.root/'scripts/ssh-known-hosts').write_text('187.77.95.158 ssh-ed25519 CLE-PUBLIQUE-SYNTHETIQUE\n')
        self.d={'format':1,'soumission_autorisee_par_proprietaire':True,
            'origine_preuves':'codex-local-non-attestee','depot':'MrJ-am/vps-infrastructure',
            'transport':'git-chiffre','revision_transport':'a'*40,'chemin_transport':'candidat.tar.gz.age',
            'revision_operateurs':'b'*40,'revision_construction':'c'*40,
            'cipher_sha256':'d'*64,'archive_sha256':'e'*64,'stage_sha256':'f'*64,
            'artefact_sha256':'1'*64,'cipher_octets':12345,
            'recipient_ssh':'ssh-ed25519 CLE-PUBLIQUE-SYNTHETIQUE'}

    def lire(self):
        (self.root/'operations/monolithe-candidat.json').write_text(json.dumps(self.d))
        with patch.object(m,'RACINE',self.root):return m.descriptor()

    def test_git_chiffre_exact(self):self.assertEqual(self.lire(),self.d)

    def test_revision_chemin_depot_non_verrouilles(self):
        for champ,valeur in [('revision_transport','main'),('chemin_transport','../secret'),
                             ('depot','tiers/depot'),('cipher_sha256','faux')]:
            with self.subTest(champ=champ):
                ancien=self.d[champ];self.d[champ]=valeur
                with self.assertRaises(ValueError):self.lire()
                self.d[champ]=ancien

    def test_recus_et_recipient_ne_suffisent_pas(self):
        self.d['soumission_autorisee_par_proprietaire']=False
        with self.assertRaises(ValueError):self.lire()
        self.d['soumission_autorisee_par_proprietaire']=True
        self.d['recipient_ssh']='ssh-ed25519 AUTRE-CLE'
        with self.assertRaises(ValueError):self.lire()

    def test_limite_et_origine(self):
        self.d['cipher_octets']=1024**3
        with self.assertRaises(ValueError):self.lire()
        self.d['cipher_octets']=100;self.d['origine_preuves']='cache-anonyme'
        with self.assertRaises(ValueError):self.lire()

    def test_bootstrap_compile_et_chemins_nix_bornes(self):
        tree=ast.parse((ROOT/'scripts/monolithe-stage.py').read_text())
        code=next(ast.literal_eval(n.value) for n in ast.walk(tree) if isinstance(n,ast.Assign)
                  and any(isinstance(t,ast.Name) and t.id=='bootstrap' for t in n.targets))
        compile(code,'bootstrap','exec')
        controle=next(line.strip() for line in code.splitlines() if 're.fullmatch' in line)
        import re
        for chemins,ok in [(['/nix/store/'+'a'*32+'-glibc-2.42'],True),
                           (['/tmp/faux'],False),(['/nix/store/'+'a'*32+'-a b'],False)]:
            if ok:exec(controle,{'re':re,'s':{'closure':chemins}})
            else:
                with self.assertRaises(AssertionError):exec(controle,{'re':re,'s':{'closure':chemins}})


if __name__=='__main__':unittest.main()
