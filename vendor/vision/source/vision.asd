(asdf:defsystem #:vision
  :description "Authenticated, documented HTTP API for Vision."
  :version "1.0.0"
  :serial t
  :components ((:file "src/package")
               (:file "src/server")))
