(asdf:defsystem "mrjam-metier"
  :description "Assemblage central des composants métier MrJ.am."
  :version "0.1.0"
  :depends-on ("vision" "vision/administration" "vision/cycle" "vision/fermeture" "mrjam-identite" "matheval")
  :serial t
  :components ((:file "lisp/serveur/package")
               (:file "lisp/serveur/matheval-http")
               (:file "lisp/serveur/vision-sql")
               (:file "lisp/serveur/vision-gestion")
               (:file "lisp/serveur/vision-cycle")
               (:file "lisp/serveur/admission-http")
               (:file "lisp/serveur/quotas")
               (:file "lisp/serveur/http")
               (:file "lisp/serveur/main")))
