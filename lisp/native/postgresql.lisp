(in-package #:mrjam-native)

(defun initialiser-postgresql (chemin)
  (unless (and (uiop:absolute-pathname-p chemin) (probe-file chemin))
    (echec-natif :chemin-libpq))
  (sb-alien:load-shared-object (namestring (truename chemin))))

(define-condition database-error (error)
  ((sqlstate :initarg :sqlstate :reader sqlstate)
   (code :initarg :code :initform nil :reader database-code)))

(sb-alien:define-alien-routine ("PQconnectdb" %pq-connect) sb-alien:system-area-pointer
  (config sb-alien:c-string))
(sb-alien:define-alien-routine ("PQstatus" %pq-status) sb-alien:int
  (connexion sb-alien:system-area-pointer))
(sb-alien:define-alien-routine ("PQfinish" %pq-finish) sb-alien:void
  (connexion sb-alien:system-area-pointer))
(sb-alien:define-alien-routine ("PQexecParams" %pq-exec) sb-alien:system-area-pointer
  (connexion sb-alien:system-area-pointer) (sql sb-alien:c-string) (n sb-alien:int)
  (types sb-alien:system-area-pointer) (valeurs sb-alien:system-area-pointer)
  (longueurs sb-alien:system-area-pointer) (formats sb-alien:system-area-pointer)
  (format-resultat sb-alien:int))
(sb-alien:define-alien-routine ("PQresultStatus" %pq-result-status) sb-alien:int
  (resultat sb-alien:system-area-pointer))
(sb-alien:define-alien-routine ("PQresultErrorField" %pq-result-error) sb-alien:c-string
  (resultat sb-alien:system-area-pointer) (champ sb-alien:int))
(sb-alien:define-alien-routine ("PQclear" %pq-clear) sb-alien:void
  (resultat sb-alien:system-area-pointer))
(sb-alien:define-alien-routine ("PQntuples" %pq-nrows) sb-alien:int
  (resultat sb-alien:system-area-pointer))
(sb-alien:define-alien-routine ("PQnfields" %pq-nfields) sb-alien:int
  (resultat sb-alien:system-area-pointer))
(sb-alien:define-alien-routine ("PQfname" %pq-fname) sb-alien:c-string
  (resultat sb-alien:system-area-pointer) (champ sb-alien:int))
(sb-alien:define-alien-routine ("PQgetisnull" %pq-null) sb-alien:int
  (resultat sb-alien:system-area-pointer) (ligne sb-alien:int) (champ sb-alien:int))
(sb-alien:define-alien-routine ("PQgetvalue" %pq-value) sb-alien:c-string
  (resultat sb-alien:system-area-pointer) (ligne sb-alien:int) (champ sb-alien:int))

(defstruct (connexion (:constructor %connexion (pointeur))) pointeur (transaction-p nil))

(defun avec-connexion (configuration fonction)
  "Connexion bornée à l'opération, jamais partagée ni conservée par une bibliothèque.
Configuration acquise au démarrage ; aucune connexion au chargement ASDF."
  (let* ((ptr (%pq-connect configuration)) (c (%connexion ptr)))
    (unwind-protect
        (progn
          (unless (and (not (zerop (sb-sys:sap-int ptr))) (zerop (%pq-status ptr)))
            ;; Ni chaîne de connexion, ni erreur libpq contenant des données.
            (error 'database-error :sqlstate "08001"))
          (requete c "SET timezone TO 'UTC'")
          (requete c "SET client_encoding TO 'UTF8'")
          (funcall fonction c))
      (unless (zerop (sb-sys:sap-int ptr)) (%pq-finish ptr))
      (setf (connexion-pointeur c) nil))))

(defun requete (connexion sql &optional parametres codes-autorises)
  "PQexecParams : valeurs liées, pas de substitution ni de multi-commandes."
  (unless (connexion-pointeur connexion) (error 'database-error :sqlstate "08003"))
  (let ((chaines nil) (pointeurs (sb-alien:make-alien sb-alien:system-area-pointer
                                                  (max 1 (length parametres)))))
    (unwind-protect
        (progn
          (loop for v in parametres for i from 0 do
            (if (eq v :null)
                (setf (sb-alien:deref pointeurs i) (sb-sys:int-sap 0))
                (progn
                  (unless (and (stringp v) (not (find #\Null v)))
                    (echec-natif :parametre-postgresql))
                  (let* ((bytes (sb-ext:string-to-octets v :external-format :utf-8 :null-terminate t))
                         (ptr (sb-alien:make-alien sb-alien:unsigned-char (length bytes))))
                    (push (cons ptr (length bytes)) chaines)
                    (loop for b across bytes for j from 0 do (setf (sb-alien:deref ptr j) b))
                    (setf (sb-alien:deref pointeurs i) (sb-alien:alien-sap ptr))))))
          (let ((res (%pq-exec (connexion-pointeur connexion) sql (length parametres)
                              (sb-sys:int-sap 0) (sb-alien:alien-sap pointeurs)
                              (sb-sys:int-sap 0) (sb-sys:int-sap 0) 0)))
            (when (zerop (sb-sys:sap-int res)) (error 'database-error :sqlstate "08006"))
            (unwind-protect
                (progn
                  (unless (member (%pq-result-status res) '(1 2))
                    (let ((code (%pq-result-error res (char-code #\M))))
                      (error 'database-error :sqlstate (or (%pq-result-error res (char-code #\C)) "XXXXX")
                             :code (and (member code codes-autorises :test #'equal) code))))
                  (loop for i below (%pq-nrows res) collect
                    (loop for j below (%pq-nfields res) collect
                      (cons (%pq-fname res j) (if (plusp (%pq-null res i j)) :null (%pq-value res i j))))))
              (%pq-clear res))))
      ;; Effacer les buffers de valeurs avant restitution au malloc natif.
      (loop for (ptr . taille) in chaines do
        (loop for j below taille do (setf (sb-alien:deref ptr j) 0))
        (sb-alien:free-alien ptr))
      (sb-alien:free-alien pointeurs))))

(defun transaction (connexion fonction &key lecture-seule)
  (when (connexion-transaction-p connexion) (echec-natif :transaction-imbriquee))
  (requete connexion (if lecture-seule "BEGIN READ ONLY" "BEGIN"))
  (setf (connexion-transaction-p connexion) t)
  (let ((termine nil))
    (unwind-protect
        (multiple-value-prog1 (funcall fonction connexion)
          (requete connexion "COMMIT") (setf termine t))
      (unless termine (ignore-errors (requete connexion "ROLLBACK")))
      (setf (connexion-transaction-p connexion) nil))))
