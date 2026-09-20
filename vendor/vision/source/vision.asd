(asdf:defsystem #:vision
  :description "Authenticated, documented HTTP API for Vision."
  :version "1.1.0"
  :serial t
  :components ((:file "src/package")
               (:file "src/json")
               (:file "src/database")
               (:file "src/mcp")
               (:file "src/server")))
