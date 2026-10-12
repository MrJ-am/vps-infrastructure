(defpackage #:mrjam-log
  (:use #:cl)
  (:export #:faire-contexte #:initialiser #:demarrer #:retour #:session
           #:deconnecter #:revoquer-autres #:cookie-session #:cookie-transaction
           #:csrf-valide-p #:log-error #:statut-erreur #:temps))
(in-package #:mrjam-log)
(define-condition log-error (error) ((statut :initarg :statut :reader statut-erreur)))
(defun refuser (&optional (statut 401)) (error 'log-error :statut statut))
(defun temps () (- (get-universal-time) 2208988800))
(defun j (o k) (vision:json-object-get o k))
(defun champ (o k) (cdr (assoc k o :test #'equal)))
