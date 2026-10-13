(in-package #:mrjam-audition)

(defun logit-db (p &optional p0)
  "Translation du logit ; pas de référence de hasard inventée. Valeurs extrêmes explicites."
  (when (null p) (return-from logit-db :absent))
  (exiger (and (realp p) (<= 0 p 1) (or (null p0) (and (realp p0) (< 0 p0 1)))) "proportion_invalide")
  (cond ((zerop p) :moins-infini) ((= p 1) :plus-infini)
        (t (* (/ 10d0 (log 10d0))
              (- (log (/ (coerce p 'double-float) (- 1d0 p)))
                 (if p0 (log (/ (coerce p0 'double-float) (- 1d0 p0))) 0d0))))))
(defun afficher-db (v)
  (case v (:absent "Non observé") (:moins-infini "−∞ dB") (:plus-infini "+∞ dB")
    (otherwise
      (exiger (realp v) "indicateur_invalide")
      (let* ((db (round v)) (centinats (round (* (- v db) (/ (log 10d0) 10d0) 100d0))))
        (if (zerop centinats) (format nil "~D dB" db) (format nil "~D:~D dB" db centinats))))))
(defun indicateur (reussites effectif &key propositions)
  (exiger (and (entier effectif 0 1000000) (entier reussites 0 effectif)
               (or (null propositions) (entier propositions 2 100))) "effectif_invalide")
  (let* ((p (and (plusp effectif) (/ reussites effectif))) (p0 (and propositions (/ 1 propositions)))
         (v (logit-db p p0)))
    ;; JSON porte des décimaux ; les effectifs exacts restent la source du ratio.
    ;; Le calcul interne ci-dessus conserve son quotient exact avant le logit.
    (objet "reussites" reussites "effectif" effectif "proportion" (if p (coerce p 'double-float) :null)
      "reference_hasard" (if p0 (coerce p0 'double-float) :null) "methode" "proportion brute, logit translaté, sans pseudo-observations"
      "db" (if (realp v) v :null) "extreme" (case v (:plus-infini "plus_infini") (:moins-infini "moins_infini") (t :null))
      "affichage" (afficher-db v) "pondération" "une production par observation ; aides séparées"
      "precision" "Effectif affiché ; cet indicateur n'est pas une probabilité de maîtrise.")))
