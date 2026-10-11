(in-package #:mrjam-metier)

(defstruct (quotas (:constructor faire-quotas))
  (entrees (make-hash-table :test #'equal))
  (verrou (sb-thread:make-mutex :name "quotas-http"))
  (maximum 4096))

(defun quota-route (methode chemin)
  ;; Mêmes fenêtres que le backend Matheval de référence. Login et activation
  ;; partagent le même budget ; une nouvelle URL ne contourne pas la limite.
  (cond ((and (equal methode "POST") (equal chemin "/matheval/api/sessions")) '("sessions" 30 3600))
        ((and (equal methode "POST") (member chemin '("/matheval/api/admin/setup" "/matheval/api/admin/login") :test #'equal)) '("connexion" 8 900))
        ((and (equal methode "PUT") (uiop:string-prefix-p "/matheval/api/sessions/" chemin)) '("reprises" 300 60))))

(defun quota-adresse (adresse)
  "Clé IPv4 canonique ou réseau IPv6 /56, comme express-rate-limit verrouillé."
  (unless (and (stringp adresse) (<= 3 (length adresse) 45)
               (every (lambda (c) (find c "0123456789abcdefABCDEF:.")) adresse))
    (return-from quota-adresse nil))
  (handler-case
      (if (find #\: adresse)
          (let ((octets (sb-bsd-sockets:make-inet6-address adresse)))
            (when (and (every #'zerop (subseq octets 0 10))
                       (or (and (= (aref octets 10) 255) (= (aref octets 11) 255))
                           (and (zerop (aref octets 10)) (zerop (aref octets 11)) (find #\. adresse))))
              (return-from quota-adresse (format nil "~{~D~^.~}" (coerce (subseq octets 12) 'list))))
            (fill octets 0 :start 7)
            (let* ((groupes (loop for i from 0 below 16 by 2 collect (+ (ash (aref octets i) 8) (aref octets (1+ i)))))
                   (debut nil) (taille 0))
              ;; Compression canonique : la première plus longue plage de zéros.
              (loop for i from 0 below 8 do
                (when (zerop (nth i groupes))
                  (let ((n (loop for j from i below 8 while (zerop (nth j groupes)) count t)))
                    (when (and (>= n 2) (> n taille)) (setf debut i taille n)))))
              (string-downcase
                (if debut
                    (format nil "~{~X~^:~}::~{~X~^:~}/56" (subseq groupes 0 debut) (subseq groupes (+ debut taille)))
                    (format nil "~{~X~^:~}/56" groupes)))))
          (let ((morceaux (uiop:split-string adresse :separator ".")))
            (when (and (= (length morceaux) 4)
                       (every (lambda (p) (and (plusp (length p)) (<= (length p) 3)
                         (or (= (length p) 1) (not (char= (char p 0) #\0)))
                         (every #'digit-char-p p) (<= (parse-integer p) 255))) morceaux))
              (format nil "~{~D~^.~}" (mapcar #'parse-integer morceaux)))))
    (error () nil)))

(defun quota-entetes (categorie adresse attente restant)
  (destructuring-bind (nom limite duree) categorie
    (declare (ignore nom))
    (let* ((identifiant (format nil "~D-in-~A" limite (case duree (3600 "1hr") (900 "15min") (60 "1min"))))
           (partition (mrjam-native:base64 (sb-ext:string-to-octets
               (subseq (mrjam-native:sha256 (quota-adresse adresse)) 0 12) :external-format :utf-8))))
      (list (cons "RateLimit" (format nil "~S; r=~D; t=~D" identifiant restant attente))
            (cons "RateLimit-Policy" (format nil "~S; q=~D; w=~D; pk=:~A:" identifiant limite duree partition))))))

(defun quota-prendre (ctx categorie adresse &optional (temps (get-internal-real-time)))
  "Adresse imposée par l'émetteur Nginx vérifié ; table bornée, horloge monotone.
Retour : autorisé, secondes avant expiration, nombre restant. Aucun utilisateur
métier ni secret dans cette table. Le redémarrage remet ces seuls budgets à zéro."
  (setf adresse (quota-adresse adresse))
  (unless adresse
    (return-from quota-prendre (values nil 0 0 :adresse)))
  (destructuring-bind (nom limite duree) categorie
    (let* ((cle (cons nom adresse)) (ticks (* duree internal-time-units-per-second)))
      (sb-thread:with-mutex ((quotas-verrou ctx))
        (let ((entry (gethash cle (quotas-entrees ctx))))
          (when (and entry (>= temps (aref entry 0)))
            (remhash cle (quotas-entrees ctx)) (setf entry nil))
          (unless entry
            (when (>= (hash-table-count (quotas-entrees ctx)) (quotas-maximum ctx))
              (maphash (lambda (k v) (when (>= temps (aref v 0)) (remhash k (quotas-entrees ctx)))) (quotas-entrees ctx)))
            (when (>= (hash-table-count (quotas-entrees ctx)) (quotas-maximum ctx))
              (return-from quota-prendre (values nil 1 0 :capacite)))
            (setf entry (vector (+ temps ticks) 0) (gethash cle (quotas-entrees ctx)) entry))
          (let ((attente (max 1 (ceiling (- (aref entry 0) temps) internal-time-units-per-second))))
            (if (>= (aref entry 1) limite) (values nil attente 0 :limite)
                (progn (incf (aref entry 1)) (values t attente (- limite (aref entry 1)) nil)))))))))
