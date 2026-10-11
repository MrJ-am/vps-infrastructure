(load (merge-pathnames "../assemblage/charger.lisp" *load-truename*))
(asdf:load-system "mrjam-metier")
(let ((racine (uiop:pathname-parent-directory-pathname
                (uiop:pathname-directory-pathname *load-truename*))))
  (load (merge-pathnames "tests/provenance-regressions.lisp" racine))
  (let ((fixtures (uiop:symbol-call :mrjam-regressions :verifier-provenance racine)))
    (mrjam-native:initialiser-crypto (or (uiop:getenv "MRJAM_LIBCRYPTO") "/lib/x86_64-linux-gnu/libcrypto.so.3"))
    (load (merge-pathnames "tests/native-differentiel.lisp" racine))
    (uiop:symbol-call :native-differentiel :verifier (merge-pathnames "native.json" fixtures))))
