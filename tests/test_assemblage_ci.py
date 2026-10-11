"""Pilote CI réel : les commits de prose n'exigent ni composants ni suites inchangées."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]

class PiloteCI(unittest.TestCase):
    def test_diffs_git_reels_et_sorties_actions(self):
        with tempfile.TemporaryDirectory(prefix='mrjam-impact-ci-') as d:
            root=Path(d);repo=root/'repo';repo.mkdir()
            (repo/'scripts').mkdir();(repo/'assemblage').mkdir();(repo/'docs').mkdir()
            for n in ('assemblage.py','ci-impact.py'):shutil.copyfile(ROOT/'scripts'/n,repo/'scripts'/n)
            shutil.copyfile(ROOT/'assemblage/suites.json',repo/'assemblage/suites.json')
            (repo/'docs/ETAT.md').write_text('Référence synthétique.\n')
            (repo/'assemblage/tables-privees.json').write_text('{}\n')
            env={k:v for k,v in os.environ.items() if k in ('PATH','HOME','LANG','LC_ALL')}
            env.update(GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL=os.devnull)
            def git(*args):
                return subprocess.check_output(['git','-c','user.name=Qualification','-c','user.email=fixture@example.test',
                  '-c','core.hooksPath=/dev/null',*args],cwd=repo,env=env,text=True,stderr=subprocess.DEVNULL).strip()
            git('init');git('add','.');git('commit','-m','Référence fixture')
            def cas(chemin,attendus):
                avant=git('rev-parse','HEAD')
                with (repo/chemin).open('a') as f:f.write('\n')
                git('add',chemin);git('commit','-m','Changement synthétique')
                sortie=root/'sorties';sortie.write_text('')
                subprocess.run(['python3','scripts/ci-impact.py'],cwd=repo,
                  env=dict(env,MRJAM_COMMIT_AVANT=avant,GITHUB_OUTPUT=str(sortie)),check=True,capture_output=True,timeout=30)
                observes=dict(l.split('=',1) for l in sortie.read_text().splitlines())
                self.assertEqual(observes,attendus)
            cas('docs/ETAT.md',dict(composants='false',test_selection='false',test_sauvegarde='false',test_schema='false'))
            cas('scripts/ci-impact.py',dict(composants='false',test_selection='true',test_sauvegarde='false',test_schema='false'))
            cas('assemblage/tables-privees.json',dict(composants='true',test_selection='false',test_sauvegarde='false',test_schema='true'))

if __name__=='__main__':unittest.main()
