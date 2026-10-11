;;; Raccordement de sources verrouillées, pas un système métier.
(require :asdf)
(require :sb-posix)
(defpackage #:mrjam-outils-mcp
  (:use #:cl)
  (:export #:initialiser #:*racine* #:*etat* #:*marqueur* #:*objet* #:*mutations*))
(in-package #:mrjam-outils-mcp)
(defvar *racine*
  (uiop:pathname-parent-directory-pathname
   (uiop:pathname-parent-directory-pathname
    (uiop:pathname-directory-pathname *load-truename*))))
(defvar *etat* (merge-pathnames "state/outils-mcp/" *racine*))
(defvar *marqueur* "amendement-20261011-image-persistante")
(defvar *objet* (vector :synthese 0))
(defvar *mutations* 0)

(defun initialiser ()
  (let* ((store (uiop:ensure-directory-pathname
                 (string-trim '(#\Newline #\Return)
                  (uiop:read-file-string
                   (merge-pathnames "state/outils-sources/mcp-store.txt" *racine*)))))
         (empreinte (subseq
                     (uiop:run-program
                      (list "sha256sum" (namestring (merge-pathnames "mcp.lock.json" store)))
                      :output :string) 0 64))
         (cache (merge-pathnames
                 (format nil "state/fasl-outils/~A-sbcl~A-asdf~A/"
                         empreinte (lisp-implementation-version) (asdf:asdf-version))
                 *racine*)))
    (assert (equal "2.6.4" (lisp-implementation-version)))
    (assert (equal "3.3.1" (asdf:asdf-version)))
    (uiop:run-program (list "mkdir" "-p" "--mode=700" (namestring *etat*) (namestring cache)))
    (let ((repertoires (remove-duplicates
                       (mapcar #'truename
                        (uiop:subdirectories (merge-pathnames "sources/" store)))
                       :test #'equal)))
      (dolist (rep repertoires)
        (pushnew rep asdf:*central-registry* :test #'equal))
      ;; MGL/autoload expose certains ASDs imbriqués : le graphe ASDF fait la recherche.
      (asdf:initialize-source-registry
       `(:source-registry ,@(mapcar (lambda (p) `(:tree ,(namestring p))) repertoires)
         :inherit-configuration)))
    ;; Le cache métier en cours reste utilisé ; seuls les outils Nix ont leur cache.
    (let* ((pkg (find-package :mrjam-assemblage))
           (sym (and pkg (find-symbol "*CACHE-REPERTOIRE*" pkg)))
           (metier (and sym (boundp sym) (symbol-value sym))))
      (asdf:initialize-output-translations
       `(:output-translations
         ("/nix/store/" ,(namestring cache))
         (t ,(namestring (or metier cache))) :ignore-inherited-configuration)))
    (sb-posix:setenv "MCP_NO_WORKER_POOL" "1" 1)
    store))
(in-package #:cl-user)
