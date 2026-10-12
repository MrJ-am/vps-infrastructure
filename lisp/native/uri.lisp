(in-package #:mrjam-native)

(defun parametre-url (texte)
  "Encodage UTF-8/RFC3986 commun aux clients HTTP, sans normalisation d'identité."
  (unless (stringp texte) (echec-natif :parametre-url))
  (with-output-to-string (sortie)
    (loop for octet across (sb-ext:string-to-octets texte :external-format :utf-8) do
      (if (or (<= 65 octet 90) (<= 97 octet 122) (<= 48 octet 57)
              (member octet '(45 46 95 126)))
          (write-char (code-char octet) sortie)
          (format sortie "%~2,'0X" octet)))))

(defun chaine-config-curl (texte)
  "Une valeur de configuration sur stdin ; aucun caractère de contrôle."
  (unless (and (stringp texte)
               (every (lambda (c) (and (>= (char-code c) 32) (/= (char-code c) 127))) texte))
    (echec-natif :configuration-curl))
  (with-output-to-string (sortie)
    (write-char #\" sortie)
    (loop for c across texte do
      (when (find c "\\\"") (write-char #\\ sortie))
      (write-char c sortie))
    (write-char #\" sortie)))
