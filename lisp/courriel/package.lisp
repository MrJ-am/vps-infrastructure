(defpackage #:mrjam-courriel
  (:use #:cl)
  (:export #:lire-prive #:lire-secret-prive #:verifier-smtp #:adresse #:faire-file
           #:ajouter #:etat #:annuler #:purger #:traiter #:archiver-effacement
           #:chiffrer #:verifier-recipient #:file-chemin #:file-expediteur #:courriel-error
           #:repertoire-prive #:journal-lire #:journal-ajouter #:maintenant))
(in-package #:mrjam-courriel)
(define-condition courriel-error (error) ((code :initarg :code :reader courriel-code)))
(defun refuse (&optional (code :parametres)) (error 'courriel-error :code code))
(defun maintenant () (- (get-universal-time) 2208988800))
(defun j (o k &optional def) (vision:json-object-get o k def))
(defun champs-p (o champs)
  (and (vision:json-object-p o) (= (length (vision:json-object-entries o)) (length champs))
       (every (lambda (k) (nth-value 1 (vision:json-object-get o k))) champs)))
(defun ascii-p (s permis minimum maximum)
  (and (stringp s) (<= minimum (length s) maximum)
       (every (lambda (c) (or (char<= #\a c #\z) (char<= #\A c #\Z) (char<= #\0 c #\9) (find c permis))) s)))
