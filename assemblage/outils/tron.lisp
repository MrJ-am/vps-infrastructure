;;; Processus d'outillage séparé : pas de chargement du serveur métier.
(load (merge-pathnames "registre.lisp" *load-truename*))
(defparameter *store-outils* (mrjam-outils-mcp:initialiser))
(load (merge-pathnames "natif.lisp" *load-truename*))
(let* ((client (merge-pathnames "sources/quicklisp-client/" *store-outils*))
       (prive (merge-pathnames "quicklisp/" mrjam-outils-mcp:*etat*)))
  (unless (probe-file (merge-pathnames "setup.lisp" prive))
    (uiop:run-program (list "cp" "-RL" (namestring client) (namestring prive))))
  ;; Le store est en lecture seule ; seule sa copie privée de configuration est writable.
  (uiop:run-program (list "chmod" "-R" "u+rwX" (namestring prive)))
  ;; Un dists vide empêche l'installation implicite d'une distribution courante.
  (ensure-directories-exist (merge-pathnames "dists/" prive))
  (load (merge-pathnames "setup.lisp" prive)))
(let ((*compile-verbose* nil) (*compile-print* nil) (*load-verbose* nil))
  ;; Sous-système officiel de serveur, sans l'outil optionnel d'installation de skills.
  (asdf:load-system "cl-tron-mcp/core"))
(setf cl-tron-mcp/config::*config-file-paths* nil)
(cl-tron-mcp/config:set-config :swank-host "127.0.0.1")
(cl-tron-mcp/config:set-config :swank-port 4105)
(cl-tron-mcp/config:set-config :http-port 4107)
;; Autorisation de la mission, bornée aux opérations de l'image de développement.
;; Pas de lancement d'image, suppression de thread ou administration distante.
(dolist (paire '((:eval . "repl_eval") (:compile-file . "repl_compile")))
  (let ((nom (cdr paire)))
    (cl-tron-mcp/security:whitelist-add
     (car paire)
     (lambda (details)
       (and (equal nom (getf details :tool))
            (equal "127.0.0.1" cl-tron-mcp/tools::*repl-host*)
            (eql 4105 cl-tron-mcp/tools::*repl-port*))))))
(cl-tron-mcp/security:whitelist-enable)
(assert (not (find-package :mrjam-metier)))
(format t "~&Tron : PID outil ~D, cible Swank4105 ; aucune application locale.~%"
        (sb-posix:getpid))
(cl-tron-mcp/core:start-server :transport :http-only :port 4107)
