"""Invalidation de toolchain/politique et refus d'un cache non fiable."""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='mrjam-cache-') as tmp:
    p=Path(tmp)
    (p/'public').mkdir(mode=0o755)
    (p/'public').chmod(0o755) # La tâche peut avoir un umask 077.
    (p/'prive').mkdir(mode=0o700)
    (p/'lien').symlink_to(p/'prive',target_is_directory=True)
    def literal(s):return '"'+str(s).replace('\\','\\\\').replace('"','\\"')+'"'
    fichier=p/'test.lisp'
    fichier.write_text(f'''(load {literal(ROOT/'assemblage/charger.lisp')})
(let* ((base mrjam-assemblage:*cache-identite*)
       (cle (mrjam-assemblage:identite-cache base)))
  (assert base)
  (dolist (champ '(:sbcl :asdf :compilateur :machine :systeme :features :optimisation :abi))
    (let ((autre (copy-list base)))
      (setf (getf autre champ) "autre environnement")
      (assert (not (equal cle (mrjam-assemblage:identite-cache autre)))))))
(assert (not (equal (asdf:apply-output-translations #P"/fixture/vision/src/package.fasl")
                    (asdf:apply-output-translations #P"/fixture/matheval/lisp/package.fasl"))))
(mrjam-assemblage::repertoire-prive (uiop:ensure-directory-pathname {literal(p/'prive')}))
(dolist (path (list {literal(p/'public')} {literal(p/'lien')}))
  (assert (handler-case (progn (mrjam-assemblage::repertoire-prive (uiop:ensure-directory-pathname path)) nil)
            (error () t))))
(format t "Cache FASL : huit invalidations, chemins distincts, permissions et liens verifies.~%")
''')
    env={k:v for k,v in os.environ.items() if k in ('PATH','HOME','SBCL_HOME','LANG','LC_ALL','MRJAM_ATELIER')}
    env['LC_ALL']='C'
    subprocess.run([os.environ.get('SBCL','sbcl'),'--script',fichier],env=env,check=True)
