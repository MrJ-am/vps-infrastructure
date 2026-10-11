(defpackage #:mrjam-native
  (:use #:cl)
  (:export #:initialiser-crypto #:sha256 #:aleatoire-hex #:aleatoire-url #:uuid #:base64 #:secret-egal-p
           #:scrypt #:mot-de-passe-encoder #:mot-de-passe-verifier
           #:json-js #:native-error #:initialiser-postgresql
           #:avec-connexion #:requete #:transaction #:database-error #:sqlstate #:database-code
           #:initialiser-sqlite #:avec-sqlite #:sqlite-requete #:sqlite-transaction #:sqlite-error))

(in-package #:mrjam-native)

(define-condition native-error (error)
  ((operation :initarg :operation :reader native-operation)))

(defun echec-natif (operation) (error 'native-error :operation operation))
