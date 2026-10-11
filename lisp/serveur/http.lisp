(in-package #:mrjam-metier)

(define-condition http-error (error)
  ((status :initarg :status :reader http-status)))
(defun erreur-http (status) (error 'http-error :status status))

(defstruct (configuration (:constructor faire-configuration (&key matheval origine document-vision executeur-vision socket (workers 32))))
  matheval origine document-vision executeur-vision socket workers)

(defun ligne-http (s maximum)
  (let ((out (make-array maximum :element-type '(unsigned-byte 8))) (n 0))
    (loop for b = (read-byte s nil nil) do
      (unless b (erreur-http 400))
      (when (= b 10)
        (unless (and (> n 0) (= (aref out (1- n)) 13)) (erreur-http 400))
        (return (sb-ext:octets-to-string out :end (1- n) :external-format :ascii)))
      (when (= n maximum) (erreur-http 431))
      (unless (or (= b 13) (= b 9) (<= 32 b 126)) (erreur-http 400))
      (setf (aref out n) b) (incf n))))

(defun lire-requete (s)
  "Framing HTTP borné en octets ; pas de Content-Length/TE ambigus."
  (let* ((premiere (ligne-http s 4096)) (parts (uiop:split-string premiere :separator " "))
         (headers nil))
    (unless (and (= (length parts) 3) (member (first parts) '("GET" "HEAD" "POST" "PUT" "DELETE" "OPTIONS") :test #'equal)
                 (uiop:string-prefix-p "/" (second parts))
                 (member (third parts) '("HTTP/1.0" "HTTP/1.1") :test #'equal)) (erreur-http 400))
    (loop for n from 0 for line = (ligne-http s 8192) do
      (when (equal line "") (return)) (when (= n 64) (erreur-http 431))
      (let ((colon (position #\: line)))
        (unless (and colon (> colon 0)
                     (every (lambda (c) (or (find c "!#$%&'*+-.^_`|~")
                                           (char<= #\a (char-downcase c) #\z) (char<= #\0 c #\9))) (subseq line 0 colon))) (erreur-http 400))
        (push (cons (string-downcase (subseq line 0 colon)) (string-trim '(#\Space #\Tab) (subseq line (1+ colon)))) headers)))
    (setf headers (nreverse headers))
    (dolist (nom '("content-length" "host" "origin" "content-type" "cookie" "x-session-token" "x-mrjam-service" "x-mrj-user"
                   "x-vision-authenticated" "x-vision-browser" "x-vision-administration" "x-matheval-request"))
      (when (> (count nom headers :key #'car :test #'equal) 1) (erreur-http 400)))
    (when (assoc "transfer-encoding" headers :test #'equal) (erreur-http 400))
    (let* ((len (or (entete headers "content-length") "0"))
           (taille (progn (unless (and (> (length len) 0) (every (lambda (c) (char<= #\0 c #\9)) len)) (erreur-http 400))
                          (parse-integer len))))
      (when (> taille (* 5 1024 1024)) (erreur-http 413))
      (when (and (> taille 0) (member (first parts) '("GET" "HEAD") :test #'equal)) (erreur-http 400))
      (let ((body (make-array taille :element-type '(unsigned-byte 8))))
        (unless (= (read-sequence body s) taille) (erreur-http 400))
        (values (first parts) (second parts) headers
                (handler-case (sb-ext:octets-to-string body :external-format :utf-8)
                  (sb-int:character-decoding-error () (erreur-http 400))))))))

(defun decode-query (texte)
  ;; Pourcentage UTF-8 strict. Une seule valeur par nom ; ne pas transformer
  ;; des paramètres répétés en tableaux implicites qui changeraient le contrat.
  (labels ((dec (text)
             (let ((out (make-array (length text) :element-type '(unsigned-byte 8))) (n 0))
               (loop for i from 0 below (length text) for c = (char text i) do
                 (cond ((char= c #\%)
                        (unless (and (< (+ i 2) (length text)) (digit-char-p (char text (1+ i)) 16) (digit-char-p (char text (+ i 2)) 16)) (erreur-http 400))
                        (setf (aref out n) (+ (* 16 (digit-char-p (char text (1+ i)) 16)) (digit-char-p (char text (+ i 2)) 16))) (incf i 2))
                       ((char= c #\+) (setf (aref out n) 32))
                       (t (setf (aref out n) (char-code c)))) (incf n))
               (handler-case (sb-ext:octets-to-string out :end n :external-format :utf-8)
                 (sb-int:character-decoding-error () (erreur-http 400))))))
    (vision::%make-json-object
      (when texte
        (let ((seen nil))
          (loop for part in (uiop:split-string texte :separator "&") unless (equal part "") collect
            (let* ((eq (position #\= part)) (k (dec (subseq part 0 eq))))
              (when (member k seen :test #'equal) (erreur-http 400)) (push k seen)
              (cons k (dec (if eq (subseq part (1+ eq)) ""))))))))))

(defun repondre-http (s status corps headers &key head)
  (let* ((bytes (sb-ext:string-to-octets corps :external-format :utf-8))
         (ctype (or (entete headers "Content-Type") "application/json; charset=utf-8"))
         (entetes (format nil "HTTP/1.1 ~D ~A~C~CContent-Type: ~A~C~CContent-Length: ~D~C~CConnection: close~C~C~{~A~}~C~C"
                          status (case status (200 "OK") (201 "Created") (400 "Bad Request") (401 "Unauthorized") (403 "Forbidden")
                                        (404 "Not Found") (409 "Conflict") (413 "Content Too Large") (431 "Request Header Fields Too Large") (t "Response"))
                          #\Return #\Linefeed ctype #\Return #\Linefeed (length bytes) #\Return #\Linefeed #\Return #\Linefeed
                          (loop for (k . v) in headers unless (string-equal k "Content-Type") collect
                            (progn (unless (and (not (find #\Return v)) (not (find #\Newline v))) (erreur-http 500))
                                   (format nil "~A: ~A~C~C" k v #\Return #\Linefeed))) #\Return #\Linefeed)))
    (write-sequence (sb-ext:string-to-octets entetes :external-format :utf-8) s)
    (unless head (write-sequence bytes s)) (finish-output s)))

(defun router (cfg s method target headers body)
  (let* ((service (entete headers "x-mrjam-service")) (q (position #\? target)) (path (subseq target 0 q)))
    ;; En production, ce champ provient exclusivement du Nginx autorisé sur le
    ;; socket Unix privé. Il ne vérifie aucune identité par lui-même.
    (cond
      ((equal service "matheval")
       (unless (uiop:string-prefix-p "/matheval/api/" path) (erreur-http 404))
       (multiple-value-bind (status value retour)
           (traiter-matheval (configuration-matheval cfg) method (subseq path 14) headers
                            (decode-query (and q (subseq target (1+ q)))) body :origine (configuration-origine cfg))
         (repondre-http s status (if (stringp value) value (mrjam-native:json-js value))
           (append retour '(("X-Content-Type-Options" . "nosniff") ("X-Frame-Options" . "DENY") ("Referrer-Policy" . "no-referrer")
                            ("Permissions-Policy" . "camera=(), microphone=(), geolocation=()")
                            ("Content-Security-Policy" . "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self' data:; connect-src 'self'; base-uri 'self'; frame-ancestors 'none'; object-src 'none'; form-action 'self'")))
           :head (equal method "HEAD"))))
      ((equal service "vision")
       (when q (erreur-http 400))
       (when (> (length (sb-ext:string-to-octets body :external-format :utf-8)) 65536) (erreur-http 413))
       (unless (member method '("GET" "POST") :test #'equal) (erreur-http 405))
       (let* ((vision::*document-root* (configuration-document-vision cfg))
              (vision::*database-executor* (configuration-executeur-vision cfg))
              (response (with-output-to-string (out) (vision:route-request out method path headers body))))
         (write-sequence (sb-ext:string-to-octets response :external-format :utf-8) s) (finish-output s)))
      (t (erreur-http 400)))))

(defun traiter-client (cfg client)
  (let ((s (sb-bsd-sockets:socket-make-stream client :input t :output t :element-type '(unsigned-byte 8) :buffering :full :auto-close t)))
    (unwind-protect
        (handler-case
            (sb-ext:with-timeout 10
              (multiple-value-bind (m target headers body) (lire-requete s) (router cfg s m target headers body)))
          (http-error (e) (ignore-errors (repondre-http s (http-status e) "{\"error\":\"invalid_request\"}" '(("Cache-Control" . "no-store")))))
          (sb-ext:timeout () (ignore-errors (repondre-http s 408 "{\"error\":\"request_timeout\"}" '(("Cache-Control" . "no-store")))))
          (error () (format *error-output* "Requête métier indisponible.~%")
                    (ignore-errors (repondre-http s 500 "{\"error\":\"internal_error\"}" '(("Cache-Control" . "no-store"))))))
      (ignore-errors (close s)))))

(defun servir (cfg)
  "Un seul listener AF_UNIX. Pas de REPL, pas d'accès TCP au backend métier."
  (let ((chemin (configuration-socket cfg)) (listener (make-instance 'sb-bsd-sockets:local-socket :type :stream))
        (slots (sb-thread:make-semaphore :count (configuration-workers cfg))))
    ;; Ne supprimer aucun chemin préexistant : le répertoire RuntimeDirectory
    ;; appartient à systemd ; un fichier inattendu fait échouer le démarrage.
    (when (probe-file chemin) (erreur-http 500))
    (unwind-protect
        (progn
          (sb-bsd-sockets:socket-bind listener chemin) (sb-posix:chmod chemin #o660)
          (sb-bsd-sockets:socket-listen listener 128)
          (loop for client = (sb-bsd-sockets:socket-accept listener) do
            (if (sb-thread:try-semaphore slots)
                (handler-case
                    (let ((c client))
                      (sb-thread:make-thread (lambda () (unwind-protect (traiter-client cfg c) (sb-thread:signal-semaphore slots))) :name "metier-http"))
                  (error () (sb-thread:signal-semaphore slots) (sb-bsd-sockets:socket-close client)))
                (sb-bsd-sockets:socket-close client))))
      (sb-bsd-sockets:socket-close listener)
      (when (probe-file chemin) (delete-file chemin)))))
