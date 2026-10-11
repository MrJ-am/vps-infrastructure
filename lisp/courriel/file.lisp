(in-package #:mrjam-courriel)

(defstruct (file (:constructor %faire-file)) chemin expediteur transport)
(defun avec-file (file fonction)
  (mrjam-native:avec-sqlite (file-chemin file) fonction))
(defun lire-colonne (row k) (cdr (assoc k row :test #'equal)))
(defun faire-file (chemin expediteur &key (transport #'transmettre))
  (let ((file (%faire-file :chemin (pathname chemin) :expediteur (adresse expediteur) :transport transport)))
    (repertoire-prive (uiop:pathname-directory-pathname (file-chemin file)))
    (avec-file file
      (lambda (db)
        (mrjam-native:sqlite-transaction db
          (lambda (db)
            (mrjam-native:sqlite-requete db "CREATE TABLE IF NOT EXISTS courriels (cle TEXT PRIMARY KEY,message BLOB NOT NULL,cree INTEGER NOT NULL,etat TEXT NOT NULL DEFAULT 'attente',essais INTEGER NOT NULL DEFAULT 0,prochain INTEGER NOT NULL DEFAULT 0,accepte INTEGER,erreur TEXT)")
            (let ((cols (mapcar (lambda (r) (lire-colonne r "name")) (mrjam-native:sqlite-requete db "PRAGMA table_info(courriels)"))))
              (dolist (col '("empreinte" "empreinte_metier"))
                (unless (member col cols :test #'equal)
                  (mrjam-native:sqlite-requete db (format nil "ALTER TABLE courriels ADD COLUMN ~A TEXT" col)))))
            (dolist (r (mrjam-native:sqlite-requete db "SELECT cle,message FROM courriels WHERE empreinte IS NULL"))
              (mrjam-native:sqlite-requete db "UPDATE courriels SET empreinte=? WHERE cle=?"
                (list (mrjam-native:sha256 (lire-colonne r "message")) (lire-colonne r "cle"))))))))
    file))

(defun etat (file cle)
  (avec-file file (lambda (db)
    (let ((row (first (mrjam-native:sqlite-requete db "SELECT etat,essais,accepte,erreur FROM courriels WHERE cle=?" (list cle)))))
      (when row (vision:jobject "etat" (lire-colonne row "etat") "essais" (lire-colonne row "essais")
                               "accepte_a" (lire-colonne row "accepte") "erreur" (lire-colonne row "erreur")))))))

(defun ajouter (file cle destinataire sujet texte &optional piece)
  (unless (ascii-p cle "_.:-" 1 160) (refuse :cle))
  (unless (and (stringp sujet) (<= (length sujet) 160) (every (lambda (c) (>= (char-code c) 32)) sujet)) (refuse :sujet))
  (unless (and (stringp texte) (<= (length (sb-ext:string-to-octets texte :external-format :utf-8)) 16000)) (refuse :texte))
  (when (and piece (not (and (typep piece '(simple-array (unsigned-byte 8) (*))) (<= (length piece) 65536)))) (refuse :piece))
  (adresse destinataire)
  (let ((hash (empreinte-contenu (file-expediteur file) destinataire sujet texte piece)))
    (avec-file file
      (lambda (db)
        (mrjam-native:sqlite-transaction db
          (lambda (db)
            (let* ((old (first (mrjam-native:sqlite-requete db "SELECT message,cree,empreinte_metier FROM courriels WHERE cle=?" (list cle))))
                   (cree (if old (lire-colonne old "cree") (maintenant)))
                   (old-hash (and old (lire-colonne old "empreinte_metier"))))
              (when (and old (eq old-hash :null))
                ;; Conserver exactement le message SMTP historique. La comparaison
                ;; porte sur son contenu décodé, pas sur le choix MIME de Python.
                (setf old-hash (apply #'empreinte-contenu (ancien-contenu (lire-colonne old "message")))))
              (when (and old (not (equal hash old-hash))) (refuse :cle-deja-utilisee))
              (if old
                  (mrjam-native:sqlite-requete db "UPDATE courriels SET empreinte_metier=? WHERE cle=?" (list hash cle))
                  (let ((bytes (message-mime cle (file-expediteur file) destinataire sujet texte piece cree)))
                    (mrjam-native:sqlite-requete db "INSERT INTO courriels(cle,message,cree,empreinte,empreinte_metier) VALUES(?,?,?,?,?)"
                      (list cle bytes cree (mrjam-native:sha256 bytes) hash)))))))))
    (fsync-repertoire (uiop:pathname-directory-pathname (file-chemin file)))
    (etat file cle)))

(defun annuler (file cle)
  (avec-file file (lambda (db) (mrjam-native:sqlite-requete db "UPDATE courriels SET etat='annule' WHERE cle=? AND etat='attente'" (list cle)))))
(defun purger (file &optional (maintenant (maintenant)))
  (avec-file file (lambda (db)
    (mrjam-native:sqlite-requete db "UPDATE courriels SET message=X'' WHERE (etat='accepte_relais' AND accepte<?) OR (etat='annule' AND cree<?)"
      (list (- maintenant (* 30 86400)) (- maintenant (* 30 86400)))))))

(defun traiter (file config &key (maintenant (maintenant)) cle)
  (verifier-smtp config)
  (avec-verrou-fichier (concatenate 'string (namestring (file-chemin file)) ".lock")
    (lambda (fd)
      (declare (ignore fd))
      (let ((rows (avec-file file (lambda (db)
                    (mrjam-native:sqlite-requete db "SELECT cle,message,essais FROM courriels WHERE etat='attente' AND prochain<=? AND (? IS NULL OR cle=?) ORDER BY cree LIMIT 20"
                      (list maintenant cle cle))))))
        (dolist (r rows)
          (let* ((id (lire-colonne r "cle"))
                 (ok (handler-case (progn (funcall (file-transport file) config (lire-colonne r "message")) t)
                       (error () nil))))
            (avec-file file (lambda (db)
              (if ok
                  (mrjam-native:sqlite-requete db "UPDATE courriels SET etat='accepte_relais',essais=essais+1,accepte=?,erreur=NULL WHERE cle=?" (list maintenant id))
                  (mrjam-native:sqlite-requete db "UPDATE courriels SET essais=essais+1,erreur='relais_indisponible',prochain=? WHERE cle=?"
                    (list (+ maintenant (min 3600 (* 60 (expt 2 (min (lire-colonne r "essais") 6))))) id)))))))
        (length rows)))))

(defun verifier-recipient (recipient)
  (unless (and (stringp recipient) (= (length recipient) 62) (uiop:string-prefix-p "age1" recipient)
               (every (lambda (c) (or (char<= #\a c #\z) (char<= #\0 c #\9))) (subseq recipient 4))) (refuse :recipient)) recipient)
(defun chiffrer (valeur recipient executable)
  (verifier-recipient recipient)
  (avec-temporaire (sb-ext:string-to-octets (mrjam-native:json-js valeur) :external-format :utf-8)
    (lambda (path)
      (let ((process (uiop:launch-program (list executable "-r" recipient)
                       :input path :output :stream :error-output nil :element-type '(unsigned-byte 8))))
        (unwind-protect
            (sb-ext:with-timeout 10
              (let* ((v (make-array 65537 :element-type '(unsigned-byte 8)))
                     (n (read-sequence v (uiop:process-info-output process)))
                     (code (progn (when (> n 65536) (refuse :chiffrement)) (uiop:wait-process process))))
                (unless (and (zerop code) (<= 1 n 65536)) (refuse :chiffrement)) (subseq v 0 n)))
          (when (uiop:process-alive-p process) (uiop:terminate-process process :urgent t))
          (ignore-errors (close (uiop:process-info-output process)))
          (ignore-errors (uiop:wait-process process)))))))

(defun archiver-effacement (file utilisateur date recipient exploitant executable)
  (unless (and (ascii-p utilisateur "_.-" 1 64) (integerp date) (> date 0)) (refuse :intention))
  (let ((cle (concatenate 'string "effacement:" (mrjam-native:sha256 (format nil "~A:~D" utilisateur date)))))
    (or (etat file cle)
        (ajouter file cle exploitant "MrJ.am — registre chiffré d’effacement"
          (format nil "Une intention d’effacement est jointe, chiffrée pour la clé de restauration.~%Conserver cette pièce pour appliquer les effacements avant toute réouverture après restauration.")
          (chiffrer (vision:jobject "version" 1 "utilisateur" utilisateur "confirmee_a" date) recipient executable)))))
