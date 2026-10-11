"""Une modification des documents chargés invalide le graphe ASDF en une image."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from assemblage import chemins_sources

source=chemins_sources(atelier=os.environ.get('MRJAM_ATELIER'))['vision']
with tempfile.TemporaryDirectory(prefix='mrjam-asdf-documents-') as tmp:
    root=Path(tmp);vision=root/'vision';vision.mkdir()
    shutil.copytree(source/'src',vision/'src');shutil.copytree(source/'docs',vision/'docs')
    shutil.copyfile(source/'vision.asd',vision/'vision.asd')
    env={k:v for k,v in os.environ.items() if k in ('PATH','HOME','LANG','LC_ALL','SBCL_HOME')}
    env['ASDF_OUTPUT_TRANSLATIONS']=f'(:output-translations (t "{root}/fasl/") :ignore-inherited-configuration)'
    # Un seul processus : chargement, modification de fixture, rechargement.
    code=f'''(require :asdf)
(require :sb-posix)
(asdf:load-asd #P"{vision}/vision.asd")
(asdf:load-system "vision/core")
(assert (not (search "TEMOIN-ASDF-DOCUMENT" vision::*instructions-mcp*)))
(let ((p #P"{vision}/docs/MCP.md"))
  (with-open-file (s p :direction :output :if-exists :append :external-format :utf-8)
    (format s "~%TEMOIN-ASDF-DOCUMENT~%"))
  ;; ASDF utilise les dates à la seconde : horloge de fixture explicite,
  ;; sans attente réelle ni modification d'un fichier du dépôt partagé.
  (let ((tstamp (+ 2 (sb-posix:stat-mtime (sb-posix:stat p)))))
    (sb-posix:utime p tstamp tstamp)))
(asdf:load-system "vision/core")
(assert (search "TEMOIN-ASDF-DOCUMENT" vision::*instructions-mcp*))
(format t "ASDF : document modifié, consommateurs rechargés dans la même image.~%")
'''
    (root/'test.lisp').write_text(code)
    subprocess.run(['sbcl','--script',root/'test.lisp'],env=env,check=True)
