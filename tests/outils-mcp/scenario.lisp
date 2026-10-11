;;; Fixture synthétique seulement : aucune donnée métier ou connexion extérieure.
(defpackage #:mrjam-qualification-mcp
  (:use #:cl)
  (:export #:operation #:calculer #:initialiser #:verifier-reprise
           #:*effets* #:*resultat* #:*session* #:*objet*))
(in-package #:mrjam-qualification-mcp)
(defvar *session* (format nil "qualification-~D-~D" (sb-posix:getpid) (get-universal-time)))
(defvar *objet* (vector :synthetique 0))
(defvar *effets* 0)
(defvar *resultat* nil)

(defun initialiser ()
  "Nouvelle campagne synthétique, appelée uniquement sans débogage suspendu."
  (setf *effets* 0 *resultat* nil *objet* (vector :synthetique 0)))

(defun calculer (base facteur)
  (declare (optimize (debug 3) (speed 0) (safety 3)))
  ;; Condition voulue ; ses deux arguments doivent rester inspectables.
  (error "Condition synthétique : base=~D, facteur=~D." base facteur))

(defun operation ()
  (declare (optimize (debug 3) (speed 0) (safety 3)))
  (let ((base 40) (facteur 2))
    (incf *effets*)
    (setf *resultat*
          (restart-case (calculer base facteur)
            (recalculer ()
              :report "Recalculer seulement, sans répéter l’effet déjà exécuté."
              (calculer base facteur))))))

(defun verifier-reprise ()
  (assert (= *effets* 1))
  (assert (= *resultat* 42))
  (assert (= (aref *objet* 1) 12))
  t)
