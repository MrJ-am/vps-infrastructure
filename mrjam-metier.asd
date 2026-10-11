(asdf:defsystem "mrjam-metier"
  :description "Assemblage central des composants métier MrJ.am."
  :version "0.1.0"
  :depends-on ("vision" "matheval")
  :serial t
  :components ((:file "lisp/serveur/package")
               (:file "lisp/serveur/matheval-http")
               (:file "lisp/serveur/vision-sql")
               (:file "lisp/serveur/http")
               (:file "lisp/serveur/main")))
