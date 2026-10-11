;;; Lancer exclusivement dans une image neuve et sans données de test/production.
(require :asdf)
(declaim (optimize (speed 1) (safety 3) (debug 1) (space 1) (compilation-speed 1)))
(load (merge-pathnames "charger.lisp" (uiop:pathname-directory-pathname *load-truename*)))
(asdf:load-system "mrjam-metier")
(let ((destination (or (uiop:getenv "MRJAM_EXECUTABLE") (error "Destination requise."))))
  ;; Pas de lecteur REPL, debugger interactif ou démarrage depuis un FASL inconnu.
  (sb-ext:save-lisp-and-die destination :toplevel #'mrjam-metier:main
                                      :executable t :compression t :purify t))
