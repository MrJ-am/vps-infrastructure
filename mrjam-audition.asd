(asdf:defsystem "mrjam-audition"
  :description "Audition, bibliothèques pédagogiques internes sans cycle de vie autonome."
  :version "0.1.0"
  :depends-on ("mrjam-audition/services" "vision")
  :serial t
  :components ((:file "lisp/audition/mcp")))

(asdf:defsystem "mrjam-audition/modele"
  :depends-on ("vision/json")
  :serial t
  :components ((:file "lisp/audition/package") (:file "lisp/audition/modele")
               (:file "lisp/audition/indicateurs")))

(asdf:defsystem "mrjam-audition/services"
  :depends-on ("mrjam-audition/modele" "mrjam-native")
  :serial t
  :components ((:file "lisp/audition/persistance") (:file "lisp/audition/services")))

(asdf:defsystem "mrjam-audition/tests"
  :depends-on ("mrjam-audition")
  :components ((:file "tests/audition"))
  :perform (asdf:test-op (o s) (declare (ignore o s))
             (assert (uiop:symbol-call :mrjam-audition-tests :verifier))))
