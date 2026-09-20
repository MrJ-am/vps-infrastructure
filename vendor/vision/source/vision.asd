(asdf:defsystem #:vision
  :description "Authenticated, documented HTTP API for Vision."
  :version "1.3.0"
  :serial t
  :components ((:file "src/package")
               (:file "src/json")
               (:file "src/database")
               (:file "src/fsrs")
               (:file "src/mcp")
               (:file "src/browser")
               (:file "src/server")))
