;;; Configuration officielle cl+ssl : DSO exactes, jamais le libssl de l'hôte.
(let ((*compile-verbose* nil) (*compile-print* nil))
  (asdf:load-system "cl+ssl/config"))
(let* ((crypto (uiop:getenv "MRJAM_LIBCRYPTO"))
       (ssl (and crypto (merge-pathnames "libssl.so.3" (uiop:pathname-directory-pathname crypto)))))
  (assert (and crypto (uiop:string-prefix-p "/nix/store/" crypto) (probe-file crypto) (probe-file ssl)))
  (eval `(cl+ssl/config:define-libcrypto-path ,crypto))
  (eval `(cl+ssl/config:define-libssl-path ,(namestring ssl))))
