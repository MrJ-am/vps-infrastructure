(asdf:defsystem "mrjam-native"
  :description "Adaptateurs internes SBCL vers les bibliothèques natives déjà approuvées."
  :version "0.1.0"
  :depends-on ("vision/json")
  :serial t
  :components ((:file "lisp/native/package")
               (:file "lisp/native/crypto")
               (:file "lisp/native/json-js")
               (:file "lisp/native/postgresql")
               (:file "lisp/native/sqlite")))
