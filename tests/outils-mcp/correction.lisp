;;; Correction enregistrée, à compiler dans l'image suspendue via Tron.
(in-package #:mrjam-qualification-mcp)
(defun calculer (base facteur)
  "Régression vérifiée avec les locaux BASE=40 et FACTEUR=2 : résultat 42."
  (declare (optimize (debug 3) (speed 0) (safety 3)))
  (+ base facteur))
