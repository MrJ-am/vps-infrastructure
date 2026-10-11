(in-package #:mrjam-metier)

(defun lier-sql-vision (sql variables)
  "Convertit seulement les paramètres des gabarits SQL internes en paramètres libpq.
Les valeurs ne sont jamais insérées dans le texte SQL ou une ligne de commande."
  (let ((noms nil) (valeurs nil))
    (values
      (with-output-to-string (out)
        (loop with i = 0 while (< i (length sql)) do
          (if (and (< (+ i 2) (length sql)) (char= (char sql i) #\:) (char= (char sql (1+ i)) #\'))
              (let* ((fin (or (position #\' sql :start (+ i 2)) (error "Gabarit SQL invalide.")))
                     (nom (subseq sql (+ i 2) fin)) (entree (assoc nom variables :test #'equal)))
                (unless entree (error "Paramètre SQL absent."))
                (unless (member nom noms :test #'equal)
                  (setf noms (append noms (list nom)) valeurs (append valeurs (list (cdr entree)))))
                (format out "$~D" (1+ (position nom noms :test #'equal))) (setf i (1+ fin)))
              (progn (write-char (char sql i) out) (incf i)))))
      valeurs)))

(defun executeur-vision (dsn)
  (lambda (operation sql variables)
    (declare (ignore operation))
    (handler-case
        (mrjam-native:avec-connexion dsn
          (lambda (c)
            (mrjam-native:transaction c
              (lambda (c)
                (let ((user (cdr (assoc "utilisateur" variables :test #'equal))))
                  (when user (mrjam-native:requete c "SELECT set_config('vision.utilisateur',$1,true)" (list user))))
                (multiple-value-bind (texte valeurs) (lier-sql-vision sql variables)
                  (let ((rows (mrjam-native:requete c texte valeurs
                                 '("quota_depasse" "texte_trop_long" "ligne_trop_longue" "limite_fiches"
                                   "limite_items_fiche" "invitation_requise" "compte_suspendu"))))
                    (unless (and rows (= 1 (length (first rows))) (stringp (cdar (first rows))))
                      (vision::database-fail "PostgreSQL returned no JSON result." "empty output"))
                    (vision:parse-json (cdar (first rows)))))))))
      (mrjam-native:database-error (e)
        ;; Seulement un code métier explicitement autorisé ou SQLSTATE ; jamais
        ;; un message SQL susceptible de contenir un contenu personnel.
        (vision::database-fail "PostgreSQL request failed."
                              (if (mrjam-native:database-code e)
                                  (concatenate 'string "ERROR:  " (mrjam-native:database-code e))
                                  (mrjam-native:sqlstate e)))))))
