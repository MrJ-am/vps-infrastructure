(in-package #:mrjam-courriel)
(sb-alien:define-alien-routine ("fgetxattr" %acl) sb-alien:long
  (fd sb-alien:int) (nom sb-alien:c-string) (val sb-alien:system-area-pointer) (taille sb-alien:unsigned-long))
(sb-alien:define-alien-routine ("flock" %flock) sb-alien:int (fd sb-alien:int) (operation sb-alien:int))

(defun repertoire-prive (path)
  ;; Aucun chmod d'un répertoire existant : une permission inattendue fait échouer.
  (let ((p (uiop:ensure-directory-pathname path)))
    (handler-case (sb-posix:mkdir p #o700)
      (sb-posix:syscall-error (e) (unless (= (sb-posix:syscall-errno e) sb-posix:eexist) (error e))))
    (mrjam-native::verifier-repertoire-prive p) p))

(defun acl-individuelle-p (bytes uid)
  (labels ((u16 (n) (+ (aref bytes n) (ash (aref bytes (1+ n)) 8)))
           (u32 (n) (+ (u16 n) (ash (u16 (+ n 2)) 16))))
    (and (= (length bytes) 44) (= (u32 0) 2)
         (loop for n from 4 by 8 for (tag droits user) in
                 (list '(1 4 4294967295) (list 2 4 uid) '(4 0 4294967295) '(16 4 4294967295) '(32 0 4294967295))
               always (and (= (u16 n) tag) (= (u16 (+ n 2)) droits) (= (u32 (+ n 4)) user))))))

(defun ouvrir-prive (path maximum)
  (let ((fd (sb-posix:open path (logior sb-posix:o-rdonly sb-posix:o-nofollow sb-posix:o-nonblock))) (ok nil))
    (unwind-protect
        (let* ((s (sb-posix:fstat fd)) (acl (make-array 256 :element-type '(unsigned-byte 8)))
               (n (sb-sys:with-pinned-objects (acl) (%acl fd "system.posix_acl_access" (sb-sys:vector-sap acl) (length acl)))))
          (unless (and (sb-posix:s-isreg (sb-posix:stat-mode s)) (= (sb-posix:stat-nlink s) 1)
                       (<= (sb-posix:stat-size s) maximum) (member (sb-posix:stat-uid s) (list 0 (sb-posix:geteuid)))
                       (if (< n 0)
                           (and (member (sb-alien:get-errno) (list sb-posix:enodata sb-posix:eopnotsupp))
                                (zerop (logand (sb-posix:stat-mode s) #o077)))
                           (and (= (logand (sb-posix:stat-mode s) #o777) #o440)
                                (acl-individuelle-p (subseq acl 0 n) (sb-posix:geteuid)))))
            (refuse :fichier-non-prive))
          (setf ok t) fd)
      (unless ok (sb-posix:close fd)))))

(defun lire-octets-prives (path &optional (maximum 65536))
  (let* ((fd (ouvrir-prive path maximum))
         (s (sb-sys:make-fd-stream fd :input t :element-type '(unsigned-byte 8) :auto-close t))
         (bytes (make-array (1+ maximum) :element-type '(unsigned-byte 8))))
    (unwind-protect
        (let ((n (read-sequence bytes s)))
          (when (> n maximum) (refuse :fichier-trop-long)) (subseq bytes 0 n))
      (close s))))

(defun lire-prive (path) (vision:parse-json (sb-ext:octets-to-string (lire-octets-prives path) :external-format :utf-8)))
(defun lire-secret-prive (path)
  (let ((v (string-trim '(#\Space #\Tab #\Newline #\Return)
                       (sb-ext:octets-to-string (lire-octets-prives path 128) :external-format :utf-8))))
    (unless (ascii-p v "_-" 43 43) (refuse :secret-invalide)) v))

(defun fsync-repertoire (path)
  (let ((fd (sb-posix:open path (logior sb-posix:o-rdonly sb-posix:o-directory sb-posix:o-nofollow))))
    (unwind-protect (sb-posix:fsync fd) (sb-posix:close fd))))

(defun avec-verrou-fichier (path fonction)
  (let ((fd (sb-posix:open path (logior sb-posix:o-rdwr sb-posix:o-creat sb-posix:o-nofollow) #o600)))
    (unwind-protect
        (progn
          (let ((s (sb-posix:fstat fd)))
            (unless (and (sb-posix:s-isreg (sb-posix:stat-mode s)) (= (sb-posix:stat-nlink s) 1)
                         (= (sb-posix:stat-uid s) (sb-posix:geteuid)) (zerop (logand (sb-posix:stat-mode s) #o077))) (refuse :fichier-non-prive)))
          (unless (zerop (%flock fd 2)) (refuse :verrou-indisponible)) (funcall fonction fd))
      (sb-posix:close fd))))

(defun journal-lire (path)
  (when (probe-file path)
    ;; Un registre contient seulement les intentions minimales, jamais les contenus.
    (with-open-stream (s (sb-sys:make-fd-stream (ouvrir-prive path (* 10 1024 1024)) :input t :external-format :utf-8 :auto-close t))
      (loop for l = (read-line s nil nil) while l collect (vision:parse-json l)))))

(defun journal-ajouter (path cle valeur fonction)
  "Intention unique, verrou et fsync avant toute conséquence extérieure."
  (avec-verrou-fichier path
    (lambda (fd)
      (let* ((s (sb-sys:make-fd-stream (sb-posix:dup fd) :input t :output t :external-format :utf-8 :auto-close t))
             (ancien (loop for l = (read-line s nil nil) while l for p = (vision:parse-json l)
                           when (equal (j p cle) valeur) return p)))
        (unwind-protect
            (or ancien (let ((p (funcall fonction)))
                         (file-position s :end) (write-line (mrjam-native:json-js p) s) (finish-output s)
                         (sb-posix:fsync fd) (fsync-repertoire (uiop:pathname-directory-pathname path)) p))
          (close s))))))
