;; Initialiser les copies durables uniquement ; pas de tâche, HTTP, SMTP ou IdP.
(load (merge-pathnames "../assemblage/charger.lisp" *load-truename*))
(asdf:load-system "mrjam-metier")
(mrjam-native:initialiser-crypto (uiop:getenv "MRJAM_LIBCRYPTO"))
(mrjam-native:initialiser-sqlite (uiop:getenv "MRJAM_LIBSQLITE"))
(let* ((root (uiop:ensure-directory-pathname (uiop:getenv "MRJAM_ETATS_ISOLES")))
       (smtp (vision:jobject "host" "smtp.protonmail.ch" "port" 587
                             "username" "fixture@example.test" "password" "synthetique000000"
                             "from_address" "fixture@example.test"
                             "starttls_required" :true "certificate_verification" :true))
       (config (vision:jobject "adresse_exploitant" "operator@example.test"
                               "recipient_age" (uiop:getenv "MRJAM_AGE_RECIPIENT")))
       (age (uiop:getenv "AGE"))
       (admission (vision-admission:faire-admission "copie-isolee"
                    (merge-pathnames "admission/" root) smtp nil)))
  (vision-cycle:faire-cycle "copie-isolee" (merge-pathnames "cycle/" root)
                            smtp config (lambda (u) (declare (ignore u)) nil) age)
  (vision-fermeture:faire-fermeture "copie-isolee" (merge-pathnames "fermeture/" root)
                                  smtp config nil admission age)
  (mrjam-courriel:faire-file (merge-pathnames "courriel/file.sqlite" root) "fixture@example.test")
  (format t "~&Copies SQLite initialisées ; aucun transport ni traitement exécuté.~%"))
