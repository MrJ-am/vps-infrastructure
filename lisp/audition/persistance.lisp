(in-package #:mrjam-audition)

(defclass depot-postgresql () ((dsn :initarg :dsn :reader depot-dsn)))
(defmethod print-object ((d depot-postgresql) s)
  (print-unreadable-object (d s :type t) (write-string "configuration masquée" s)))
(defgeneric avec-depot (depot acteur groupe fonction))
(defgeneric lire (base id))
(defgeneric ecrire (base id groupe nature revision document acteur temps))
(defgeneric version (base id revision))
(defgeneric lister (base groupe nature))
(defgeneric role (base groupe acteur))
(defgeneric groupes (base acteur))
(defgeneric administrateur-p (base acteur))
(defgeneric membres (base groupe))
(defgeneric changer-membre (base groupe acteur role auteur temps))
(defgeneric creer-groupe (base id nom auteur temps))
(defgeneric requete-idempotente (base acteur cle))
(defgeneric retenir-requete (base acteur cle groupe operation empreinte resultat temps))
(defgeneric supprimer-groupe (base groupe auteur temps))
(defgeneric diagnostic (base))

(defmethod avec-depot ((d depot-postgresql) acteur groupe fonction)
  (mrjam-native:avec-connexion (depot-dsn d)
    (lambda (c) (mrjam-native:transaction c
      (lambda (c)
        (mrjam-native:requete c "SELECT set_config('audition.acteur',$1,true)" (list acteur))
        ;; Un groupe est une unité de concurrence. Relecture des habilitations,
        ;; idempotence et écriture sont sous le même verrou transactionnel.
        (mrjam-native:requete c "SELECT pg_advisory_xact_lock(hashtextextended($1,37))" (list (or groupe "audition-administration")))
        (funcall fonction c))))))
(defun champ-sql (row cle) (cdr (assoc cle row :test #'equal)))
(defun json-sql (row cle) (let ((v (champ-sql row cle))) (and v (not (eq v :null)) (vision:parse-json v))))
(defmethod lire ((c mrjam-native::connexion) id)
  (let ((r (first (mrjam-native:requete c "SELECT id,groupe,nature,revision,document::text FROM audition.objets WHERE id=$1" (list id)))))
    (when r (objet "id" (champ-sql r "id") "groupe" (champ-sql r "groupe") "nature" (champ-sql r "nature")
                   "revision" (parse-integer (champ-sql r "revision")) "document" (json-sql r "document")))))
(defmethod ecrire ((c mrjam-native::connexion) id groupe nature revision document acteur temps)
  (let* ((doc (vision:json-encode document)) (v (write-to-string revision)) (date (write-to-string temps)))
    (mrjam-native:requete c
      "INSERT INTO audition.objets(id,groupe,nature,revision,document,modifie_a) VALUES($1,$2,$3,$4::bigint,$5::jsonb,to_timestamp($6::bigint))
       ON CONFLICT(id) DO UPDATE SET revision=excluded.revision,document=excluded.document,modifie_a=excluded.modifie_a
       WHERE audition.objets.groupe=excluded.groupe AND audition.objets.nature=excluded.nature AND audition.objets.revision=excluded.revision-1"
      (list id groupe nature v doc date))
    (mrjam-native:requete c
      "INSERT INTO audition.versions(objet,groupe,revision,document,auteur,recu_a) VALUES($1,$2,$3::bigint,$4::jsonb,$5,to_timestamp($6::bigint))"
      (list id groupe v doc acteur date)))
  (lire c id))
(defmethod version ((c mrjam-native::connexion) id revision)
  (json-sql (first (mrjam-native:requete c "SELECT document::text FROM audition.versions WHERE objet=$1 AND revision=$2::bigint"
                                      (list id (write-to-string revision)))) "document"))
(defmethod lister ((c mrjam-native::connexion) groupe nature)
  ;; Les listes de séances ne chargent jamais tous les corpus de productions.
  ;; La synthèse est calculée par les mêmes services à chaque écriture ; le
  ;; détail reste une lecture explicite, bornée et autorisée de la séance.
  (mapcar (lambda (r) (objet "id" (champ-sql r "id") "groupe" (champ-sql r "groupe")
       "nature" (champ-sql r "nature") "revision" (parse-integer (champ-sql r "revision")) "document" (json-sql r "document")))
    (mrjam-native:requete c
      "SELECT id,groupe,nature,revision,(CASE WHEN nature='seance' THEN document-'tentatives'-'rectifications'-'transitions' ||
        '{\"tentatives\":[],\"rectifications\":[],\"transitions\":[]}'::jsonb ELSE document END)::text AS document
       FROM audition.objets WHERE groupe=$1 AND nature=$2 ORDER BY id LIMIT 2001" (list groupe nature))))
(defmethod role ((c mrjam-native::connexion) groupe acteur)
  (champ-sql (first (mrjam-native:requete c "SELECT role FROM audition.membres WHERE groupe=$1 AND acteur=$2" (list groupe acteur))) "role"))
(defmethod administrateur-p ((c mrjam-native::connexion) acteur)
  (equal "t" (champ-sql (first (mrjam-native:requete c "SELECT actif FROM audition.administrateurs WHERE acteur=$1" (list acteur))) "actif")))
(defmethod groupes ((c mrjam-native::connexion) acteur)
  (mapcar (lambda (r) (objet "id" (champ-sql r "id") "nom" (champ-sql r "nom") "role" (or (champ-sql r "role") "administrateur")))
    (mrjam-native:requete c
      "SELECT g.id,g.nom,m.role FROM audition.groupes g LEFT JOIN audition.membres m ON m.groupe=g.id AND m.acteur=$1
       WHERE m.acteur=$1 OR EXISTS(SELECT FROM audition.administrateurs WHERE acteur=$1 AND actif) ORDER BY g.nom,g.id LIMIT 501" (list acteur))))
(defmethod membres ((c mrjam-native::connexion) groupe)
  (mapcar (lambda (r) (objet "acteur" (champ-sql r "acteur") "role" (champ-sql r "role")))
          (mrjam-native:requete c "SELECT acteur,role FROM audition.membres WHERE groupe=$1 ORDER BY acteur LIMIT 501" (list groupe))))
(defmethod changer-membre ((c mrjam-native::connexion) groupe acteur role auteur temps)
  (let ((ancien (role c groupe acteur)))
  (if (equal role "retirer")
      (mrjam-native:requete c "DELETE FROM audition.membres WHERE groupe=$1 AND acteur=$2" (list groupe acteur))
      (mrjam-native:requete c "INSERT INTO audition.membres(groupe,acteur,role) VALUES($1,$2,$3) ON CONFLICT(groupe,acteur) DO UPDATE SET role=excluded.role"
                            (list groupe acteur role)))
  (mrjam-native:requete c "INSERT INTO audition.audit(groupe,auteur,operation,cible,recu_a,details) VALUES($1,$2,$3,$4,to_timestamp($5::bigint),$6::jsonb)"
                        (list groupe auteur "habilitation" acteur (write-to-string temps)
                          (vision:json-encode (objet "ancien_role" (or ancien :null) "nouveau_role" role))))))
(defmethod creer-groupe ((c mrjam-native::connexion) id nom auteur temps)
  (mrjam-native:requete c "INSERT INTO audition.groupes(id,nom) VALUES($1,$2)" (list id nom))
  (mrjam-native:requete c "INSERT INTO audition.audit(groupe,auteur,operation,cible,recu_a) VALUES($1,$2,'creer_groupe',$1,to_timestamp($3::bigint))"
                        (list id auteur (write-to-string temps))))
(defmethod requete-idempotente ((c mrjam-native::connexion) acteur cle)
  (let ((r (first (mrjam-native:requete c "SELECT operation,empreinte,resultat::text FROM audition.requetes WHERE acteur=$1 AND cle=$2" (list acteur cle)))))
    (when r (objet "operation" (champ-sql r "operation") "empreinte" (champ-sql r "empreinte") "resultat" (json-sql r "resultat")))))
(defmethod retenir-requete ((c mrjam-native::connexion) acteur cle groupe operation empreinte resultat temps)
  (mrjam-native:requete c "INSERT INTO audition.requetes(acteur,cle,groupe,operation,empreinte,resultat,recu_a) VALUES($1,$2,$3,$4,$5,$6::jsonb,to_timestamp($7::bigint))"
                        (list acteur cle (or groupe :null) operation empreinte (vision:json-encode resultat) (write-to-string temps))))
(defmethod supprimer-groupe ((c mrjam-native::connexion) groupe auteur temps)
  ;; Suppression demandée avec confirmation explicite ; aucune restauration
  ;; d'une ancienne sauvegarde n'est utilisée pour annuler du code.
  (mrjam-native:requete c "DELETE FROM audition.groupes WHERE id=$1" (list groupe))
  (mrjam-native:requete c "INSERT INTO audition.audit(groupe,auteur,operation,cible,recu_a) VALUES(NULL,$1,'supprimer_groupe',$2,to_timestamp($3::bigint))"
                        (list auteur groupe (write-to-string temps))))
(defmethod diagnostic ((c mrjam-native::connexion))
  (objet "schema" (parse-integer (champ-sql (first (mrjam-native:requete c "SELECT max(version) AS n FROM audition.schema_migrations")) "n"))
    "base" "accessible" "donnees_pedagogiques" "non exposées par le diagnostic"))

(defstruct (service (:constructor %service)) depot (horloge #'maintenant))
(defun faire-service (dsn)
  (exiger (texte-p dsn 4096) "configuration_indisponible" 503)
  (%service :depot (make-instance 'depot-postgresql :dsn dsn)))
