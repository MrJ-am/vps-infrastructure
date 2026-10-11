(in-package #:mrjam-courriel)

(defun verifier-smtp (c)
  (unless (and (champs-p c '("host" "port" "username" "password" "from_address" "starttls_required" "certificate_verification"))
               (equal (j c "host") "smtp.protonmail.ch") (eql (j c "port") 587)
               (eq (j c "starttls_required") :true) (eq (j c "certificate_verification") :true)
               (ascii-p (j c "password") "" 16 128)
               (string-equal (adresse (j c "username")) (adresse (j c "from_address")))) (refuse :smtp)) c)

(defun config-curl (s)
  (unless (and (stringp s) (every (lambda (c) (>= (char-code c) 32)) s)) (refuse :configuration-curl))
  (with-output-to-string (o) (write-char #\" o)
    (loop for c across s do (when (find c "\\\"") (write-char #\\ o)) (write-char c o)) (write-char #\" o)))

(defun avec-temporaire (bytes fonction)
  (let* ((dir (repertoire-prive (format nil "/tmp/mrjam-metier-~D/" (sb-posix:geteuid))))
         (p (merge-pathnames (concatenate 'string "message-" (mrjam-native:aleatoire-hex 16)) dir))
         (fd (sb-posix:open p (logior sb-posix:o-wronly sb-posix:o-creat sb-posix:o-excl sb-posix:o-nofollow) #o600)))
    (unwind-protect
        (progn
          (with-open-stream (s (sb-sys:make-fd-stream fd :output t :element-type '(unsigned-byte 8) :auto-close t))
            (write-sequence bytes s) (finish-output s))
          (setf fd nil) (funcall fonction p))
      (when fd (ignore-errors (sb-posix:close fd)))
      (when (probe-file p) (delete-file p)))))

(defun transmettre (config bytes)
  "Curl déjà employé par Vision ; secrets sur stdin, message privé et temporaire.
Aucune authentification avant STARTTLS ; aucun proxy ou fallback en clair."
  (verifier-smtp config)
  (let ((curl (uiop:getenv "MRJAM_CURL")) (ca (uiop:getenv "MRJAM_CA_FILE")))
    (unless (and curl ca (uiop:absolute-pathname-p curl) (probe-file curl) (uiop:absolute-pathname-p ca) (probe-file ca)) (refuse :transport))
    (multiple-value-bind (headers body)
        (separer-mime (normaliser-lignes (sb-ext:octets-to-string bytes :external-format :utf-8)))
      (declare (ignore body))
      (let ((de (adresse (cdr (assoc "from" headers :test #'equal)))) (a (adresse (cdr (assoc "to" headers :test #'equal)))))
        (unless (string-equal de (j config "from_address")) (refuse :expediteur))
        (avec-temporaire bytes
          (lambda (path)
            (let ((input
                    (with-output-to-string (o)
                      (format o "silent~%show-error~%max-time = 20~%connect-timeout = 5~%proxy = \"\"~%noproxy = \"*\"~%proto = \"=smtp\"~%url = \"smtp://smtp.protonmail.ch:587\"~%ssl-reqd~%tlsv1.2~%")
                      (loop for (k . v) in (list (cons "cacert" ca) (cons "user" (concatenate 'string (j config "username") ":" (j config "password")))
                                               (cons "mail-from" de) (cons "mail-rcpt" a)) do
                        (format o "~A = ~A~%" k (config-curl v))))))
              (let ((p (sb-ext:run-program curl (list "--disable" "--config" "-" "--upload-file" (namestring path))
                         :input :stream :output nil :error nil :wait nil :external-format :utf-8)))
                (unwind-protect
                    (sb-ext:with-timeout 25
                      (write-string input (sb-ext:process-input p)) (finish-output (sb-ext:process-input p))
                      (close (sb-ext:process-input p)) (sb-ext:process-wait p)
                      (unless (eql (sb-ext:process-exit-code p) 0) (refuse :relais-indisponible)))
                  (when (sb-ext:process-alive-p p) (sb-ext:process-kill p sb-posix:sigkill))
                  (sb-ext:process-close p))))))))))
