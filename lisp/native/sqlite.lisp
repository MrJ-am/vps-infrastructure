(in-package #:mrjam-native)
(require :sb-posix)

(define-condition sqlite-error (error) ((code :initarg :code :reader sqlite-code)))
(defun erreur-sqlite (code) (error 'sqlite-error :code code))
(defun initialiser-sqlite (chemin)
  (unless (and (uiop:absolute-pathname-p chemin) (probe-file chemin)) (echec-natif :chemin-sqlite))
  (sb-alien:load-shared-object (namestring (truename chemin))))

(sb-alien:define-alien-routine ("sqlite3_open_v2" %sqlite-open) sb-alien:int
  (chemin sb-alien:c-string) (db (* sb-alien:system-area-pointer)) (flags sb-alien:int) (vfs sb-alien:system-area-pointer))
(sb-alien:define-alien-routine ("sqlite3_close" %sqlite-close) sb-alien:int (db sb-alien:system-area-pointer))
(sb-alien:define-alien-routine ("sqlite3_busy_timeout" %sqlite-timeout) sb-alien:int (db sb-alien:system-area-pointer) (ms sb-alien:int))
(sb-alien:define-alien-routine ("sqlite3_prepare_v2" %sqlite-prepare) sb-alien:int
  (db sb-alien:system-area-pointer) (sql sb-alien:c-string) (n sb-alien:int)
  (stmt (* sb-alien:system-area-pointer)) (tail sb-alien:system-area-pointer))
(sb-alien:define-alien-routine ("sqlite3_finalize" %sqlite-finalize) sb-alien:int (stmt sb-alien:system-area-pointer))
(sb-alien:define-alien-routine ("sqlite3_step" %sqlite-step) sb-alien:int (stmt sb-alien:system-area-pointer))
(sb-alien:define-alien-routine ("sqlite3_bind_parameter_count" %sqlite-nparams) sb-alien:int (stmt sb-alien:system-area-pointer))
(sb-alien:define-alien-routine ("sqlite3_bind_null" %sqlite-bind-null) sb-alien:int (stmt sb-alien:system-area-pointer) (i sb-alien:int))
(sb-alien:define-alien-routine ("sqlite3_bind_int64" %sqlite-bind-int) sb-alien:int (stmt sb-alien:system-area-pointer) (i sb-alien:int) (val sb-alien:long-long))
(sb-alien:define-alien-routine ("sqlite3_bind_text" %sqlite-bind-text) sb-alien:int
  (stmt sb-alien:system-area-pointer) (i sb-alien:int) (val sb-alien:system-area-pointer) (n sb-alien:int) (destructor sb-alien:system-area-pointer))
(sb-alien:define-alien-routine ("sqlite3_bind_blob" %sqlite-bind-blob) sb-alien:int
  (stmt sb-alien:system-area-pointer) (i sb-alien:int) (val sb-alien:system-area-pointer) (n sb-alien:int) (destructor sb-alien:system-area-pointer))
(sb-alien:define-alien-routine ("sqlite3_column_count" %sqlite-ncolumns) sb-alien:int (stmt sb-alien:system-area-pointer))
(sb-alien:define-alien-routine ("sqlite3_column_name" %sqlite-name) sb-alien:c-string (stmt sb-alien:system-area-pointer) (i sb-alien:int))
(sb-alien:define-alien-routine ("sqlite3_column_type" %sqlite-type) sb-alien:int (stmt sb-alien:system-area-pointer) (i sb-alien:int))
(sb-alien:define-alien-routine ("sqlite3_column_int64" %sqlite-int) sb-alien:long-long (stmt sb-alien:system-area-pointer) (i sb-alien:int))
(sb-alien:define-alien-routine ("sqlite3_column_double" %sqlite-double) sb-alien:double (stmt sb-alien:system-area-pointer) (i sb-alien:int))
(sb-alien:define-alien-routine ("sqlite3_column_text" %sqlite-text) sb-alien:system-area-pointer (stmt sb-alien:system-area-pointer) (i sb-alien:int))
(sb-alien:define-alien-routine ("sqlite3_column_blob" %sqlite-blob) sb-alien:system-area-pointer (stmt sb-alien:system-area-pointer) (i sb-alien:int))
(sb-alien:define-alien-routine ("sqlite3_column_bytes" %sqlite-bytes) sb-alien:int (stmt sb-alien:system-area-pointer) (i sb-alien:int))

(defstruct (sqlite-connexion (:constructor %sqlite-connexion (pointeur))) pointeur (transaction-p nil))

(defun verifier-repertoire-prive (p)
  (let ((s (sb-posix:lstat (namestring p))))
    (unless (and (sb-posix:s-isdir (sb-posix:stat-mode s)) (zerop (logand (sb-posix:stat-mode s) #o077))
                 (= (sb-posix:stat-uid s) (sb-posix:geteuid))) (echec-natif :repertoire-non-prive))))

(defun avec-sqlite (chemin fonction)
  "SQLite existant ; pas de connexion au chargement. État privé, NOFOLLOW, FULLMUTEX."
  (unless (and (uiop:absolute-pathname-p chemin) (not (find #\Null (namestring chemin)))) (echec-natif :chemin-sqlite))
  (verifier-repertoire-prive (uiop:pathname-directory-pathname chemin))
  (handler-case
      (let ((s (sb-posix:lstat (namestring chemin))))
        (unless (and (sb-posix:s-isreg (sb-posix:stat-mode s)) (= 1 (sb-posix:stat-nlink s))
                     (= (sb-posix:stat-uid s) (sb-posix:geteuid)) (zerop (logand (sb-posix:stat-mode s) #o077)))
          (echec-natif :fichier-sqlite-non-prive)))
    (sb-posix:syscall-error (e) (unless (= (sb-posix:syscall-errno e) sb-posix:enoent) (error e))))
  (sb-alien:with-alien ((ptr sb-alien:system-area-pointer (sb-sys:int-sap 0)))
    (let ((code (%sqlite-open (namestring chemin) (sb-alien:addr ptr) (logior 2 4 #x10000 #x1000000) (sb-sys:int-sap 0))))
      (unwind-protect
          (progn
            (unless (zerop code) (erreur-sqlite code))
            (sb-posix:chmod chemin #o600)
            (let ((db (%sqlite-connexion ptr)))
              (%sqlite-timeout ptr 30000)
              (sqlite-requete db "PRAGMA synchronous=FULL")
              (sqlite-requete db "PRAGMA journal_mode=DELETE")
              (funcall fonction db)))
        (unless (zerop (sb-sys:sap-int ptr)) (%sqlite-close ptr))))))

(defun copier-sqlite (ptr n)
  (when (> n (* 1024 1024)) (echec-natif :valeur-sqlite-trop-longue))
  (let ((bytes (make-array n :element-type '(unsigned-byte 8))))
    (dotimes (i n bytes) (setf (aref bytes i) (sb-sys:sap-ref-8 ptr i)))))

(defun sqlite-requete (db sql &optional parametres)
  "Une instruction interne, valeurs liées ; les erreurs ne contiennent ni SQL ni contenu."
  (sb-alien:with-alien ((stmt sb-alien:system-area-pointer (sb-sys:int-sap 0)))
    (let ((code (%sqlite-prepare (sqlite-connexion-pointeur db) sql -1 (sb-alien:addr stmt) (sb-sys:int-sap 0))))
      (unwind-protect
          (progn
            (unless (zerop code) (erreur-sqlite code))
            (unless (= (%sqlite-nparams stmt) (length parametres)) (echec-natif :parametres-sqlite))
            (loop for v in parametres for i from 1 do
              (let ((code
                      (cond ((or (null v) (eq v :null)) (%sqlite-bind-null stmt i))
                            ((typep v '(signed-byte 64)) (%sqlite-bind-int stmt i v))
                            ((or (stringp v) (typep v '(simple-array (unsigned-byte 8) (*))))
                             (let ((bytes (if (stringp v) (sb-ext:string-to-octets v :external-format :utf-8) v)))
                               (sb-sys:with-pinned-objects (bytes)
                                 (funcall (if (stringp v) #'%sqlite-bind-text #'%sqlite-bind-blob)
                                          stmt i (sb-sys:vector-sap bytes) (length bytes)
                                          ;; SQLITE_TRANSIENT : copie avant le retour ; ABI 64 bits verrouillée.
                                          (sb-sys:int-sap #xffffffffffffffff)))))
                            (t (echec-natif :type-sqlite)))))
                (unless (zerop code) (erreur-sqlite code))))
            (loop for step = (%sqlite-step stmt)
                  while (= step 100) collect
                  (loop for j below (%sqlite-ncolumns stmt) collect
                    (cons (%sqlite-name stmt j)
                      (case (%sqlite-type stmt j)
                        (1 (%sqlite-int stmt j)) (2 (%sqlite-double stmt j))
                        (3 (sb-ext:octets-to-string (copier-sqlite (%sqlite-text stmt j) (%sqlite-bytes stmt j)) :external-format :utf-8))
                        (4 (copier-sqlite (%sqlite-blob stmt j) (%sqlite-bytes stmt j)))
                        (5 :null) (t (echec-natif :type-colonne-sqlite)))))
                  into rows finally (unless (= step 101) (erreur-sqlite step)) (return rows)))
        (unless (zerop (sb-sys:sap-int stmt)) (%sqlite-finalize stmt))))))

(defun sqlite-transaction (db fonction)
  (when (sqlite-connexion-transaction-p db) (echec-natif :transaction-sqlite-imbriquee))
  (sqlite-requete db "BEGIN IMMEDIATE") (setf (sqlite-connexion-transaction-p db) t)
  (let ((termine nil))
    (unwind-protect
        (multiple-value-prog1 (funcall fonction db)
          (sqlite-requete db "COMMIT") (setf termine t))
      (unless termine (ignore-errors (sqlite-requete db "ROLLBACK")))
      (setf (sqlite-connexion-transaction-p db) nil))))
