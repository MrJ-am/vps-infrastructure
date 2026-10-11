;;; Atelier interactif : chargement unique, rechargement ASDF et contrôles ciblés.
;;; Aucun démarrage de serveur, accès à une base ou installation d'outil.
(load (merge-pathnames "charger.lisp" *load-truename*))
(defpackage #:mrjam-developpement
  (:use #:cl)
  (:export #:recharger #:verifier))
(in-package #:mrjam-developpement)
(defparameter *racine*
  (uiop:pathname-parent-directory-pathname
    (uiop:pathname-directory-pathname *load-truename*)))

(defun recharger (&optional (systeme "mrjam-metier"))
  "Recharger les sources modifiées par le graphe ASDF dans l'image courante."
  (asdf:load-system systeme))

(defun verifier (&rest controles)
  "Contrôles Lisp locaux ; aucun lancement de Node ni nouvelle image SBCL.
Les durées et allocations sont des diagnostics, pas des reçus de publication.
Une condition d'échec reste inspectable dans le débogueur de cette image."
  (dolist (nom controles)
    (unless (member nom '("matheval" "native" "json" "quotas") :test #'equal)
      (error "Contrôle Lisp inconnu : ~A." nom)))
  (unless controles (error "Indiquer au moins un contrôle ciblé."))
  (recharger)
  (dolist (nom controles t)
    (let ((debut (get-internal-real-time))
          (allocations (sb-ext:get-bytes-consed)))
      (cond
        ((equal nom "matheval")
         (load (merge-pathnames "assemblage/test-pures.lisp" *racine*)))
        ((equal nom "native") (load (merge-pathnames "tests/native-regressions.lisp" *racine*)))
        ((equal nom "json") (load (merge-pathnames "tests/json-commun.lisp" *racine*)))
        ((equal nom "quotas") (load (merge-pathnames "tests/quotas-http.lisp" *racine*))))
      (format t "~&~A : ~,4F s, ~D octets alloués ; contrôle local dans cette image.~%"
              nom (/ (- (get-internal-real-time) debut)
                     (float internal-time-units-per-second 1d0))
              (- (sb-ext:get-bytes-consed) allocations)))))

(recharger)
(assert (equal '(1144304738 1416247 958946056 627933444)
               (let ((tirage (matheval:generateur-32 0)))
                 (loop repeat 4 collect (funcall tirage)))))
(format t "~&Atelier chargé : SBCL ~A / ASDF ~A ; contrôle initial réussi.~%"
        (lisp-implementation-version) (asdf:asdf-version))
(in-package #:cl-user)
