;;; Système interne de test seulement, absent du graphe produit.
(asdf:defsystem "mrjam-outils-qualification"
  :serial t
  :components ((:file "scenario"))
  :in-order-to ((asdf:test-op (asdf:load-op "mrjam-outils-qualification")))
  :perform (asdf:test-op (op systeme)
              (declare (ignore op systeme))
              (assert (uiop:symbol-call :mrjam-qualification-mcp :verifier-reprise))
              (format t "~&MRJAM-MCP-ASDF:3-ASSERTIONS-REUSSIES~%")))
