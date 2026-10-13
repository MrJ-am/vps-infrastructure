(defpackage #:mrjam-log-presentation-tests (:use #:cl) (:export #:appeler))
(in-package #:mrjam-log-presentation-tests)

(defun appeler (path)
  (let* ((d (vision:parse-json (uiop:read-file-string path)))
         (headers (loop for (k . v) in (vision:json-object-entries (vision:json-object-get d "headers"))
                        collect (cons (string-downcase k) v))))
    (setf headers (append '(("x-forwarded-host" . "log.mrj.am") ("x-forwarded-proto" . "https")) headers))
    (with-open-file (s (vision:json-object-get d "sortie") :direction :output
                      :element-type '(unsigned-byte 8) :if-exists :supersede)
      (handler-case
          (mrjam-metier::router-presentation-log mrjam-log-kanidm-tests::*contexte* s
             "POST" "/presentation/api" headers (vision:json-object-get d "corps"))
        (mrjam-metier:http-error (c)
          (mrjam-metier::log-json s (mrjam-metier:http-status c) (vision:jobject "error" "requete_refusee"))))))
  :termine)
