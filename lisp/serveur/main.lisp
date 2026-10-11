(in-package #:mrjam-metier)

(defun obligatoire (nom)
  (or (uiop:getenv nom) (error "Configuration requise : ~A" nom)))

(defun secret-fichier (nom)
  (let ((path (uiop:getenv nom)))
    (when path (string-trim '(#\Space #\Tab #\Newline #\Return) (uiop:read-file-string path)))))

(defun main ()
  (handler-case
      (progn
        ;; Cette fonction est la seule entrée de l'exécutable propre : les DSO,
        ;; connexions et secrets n'existent jamais dans l'image de construction.
        (mrjam-native:initialiser-crypto (obligatoire "MRJAM_LIBCRYPTO"))
        (mrjam-native:initialiser-postgresql (obligatoire "MRJAM_LIBPQ"))
        (sb-sys:enable-interrupt sb-posix:sigterm
          (lambda (&rest ignores) (declare (ignore ignores)) (sb-ext:exit :code 0 :abort nil)))
        (servir (faire-configuration
                  :matheval (matheval:faire-contexte :connexion (obligatoire "MATHEVAL_DSN")
                              :version (obligatoire "MATHEVAL_BANK_VERSION") :activation (secret-fichier "MATHEVAL_SETUP_HASH_FILE"))
                  :origine (obligatoire "MATHEVAL_ORIGIN")
                  :document-vision (obligatoire "VISION_DOCUMENT_ROOT")
                  :executeur-vision (executeur-vision (obligatoire "VISION_DSN"))
                  :socket (obligatoire "MRJAM_SOCKET"))))
    (error ()
      ;; Ni formulaire, ni conditions contenant paramètres/chemins secrets.
      (format *error-output* "Démarrage métier refusé : configuration ou dépendance indisponible.~%")
      (finish-output *error-output*) (sb-ext:exit :code 1))))
