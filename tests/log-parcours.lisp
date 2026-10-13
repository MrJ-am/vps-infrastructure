(defpackage #:mrjam-log-parcours-tests (:use #:cl) (:export #:demarrer #:terminer #:mcp))
(in-package #:mrjam-log-parcours-tests)
(defun demarrer (p)
  (let ((d (mrjam-log-kanidm-tests::lire p)))
    (multiple-value-bind (uri cookie)
        (mrjam-log:demarrer mrjam-log-kanidm-tests::*contexte* "vision.mrj.am" "/")
      (mrjam-log-kanidm-tests::sauvegarder (mrjam-log-kanidm-tests::j d "resultat")
        (vision:jobject "uri" uri "cookie" cookie)))))
(defun terminer (p)
  (let* ((d (mrjam-log-kanidm-tests::lire p)) (ancien mrjam-log-kanidm-tests::*cookie*))
    (multiple-value-bind (retour cookie efface)
        (mrjam-log:retour mrjam-log-kanidm-tests::*contexte* "vision.mrj.am"
            (mrjam-log-kanidm-tests::j d "state") (mrjam-log-kanidm-tests::j d "code")
            (mrjam-log-kanidm-tests::j d "cookie"))
      (assert (equal retour "/")) (assert (search "Max-Age=0" efface))
      (setf mrjam-log-kanidm-tests::*cookie* cookie))
    (let ((contexte mrjam-log-kanidm-tests::*contexte*))
      (assert (mrjam-log:session contexte "vision.mrj.am" mrjam-log-kanidm-tests::*cookie*))
      ;; Une nouvelle connexion ne révoque pas la page déjà connectée.
      (when ancien (assert (mrjam-log:session contexte "vision.mrj.am" ancien))))))
(defun mcp ()
  (let* ((c mrjam-log-kanidm-tests::*contexte*) (cookies mrjam-log-kanidm-tests::*cookie*)
         (v (mrjam-native:aleatoire-url))
         (q (vision:jobject "client_id" (make-string 32 :initial-element #\A)
              "redirect_uri" "https://client.example.test/callback" "response_type" "code"
              "state" "fixture-parcours" "code_challenge_method" "S256" "scope" "vision:mcp"
              "code_challenge" (mrjam-native:base64 (mrjam-native::digest-octets (mrjam-native::octets v))
                                 :url t :sans-remplissage t))))
    (let ((id (mrjam-log::demander-mcp c cookies q)))
      (assert (equal "ChatGPT fixture" (mrjam-log-kanidm-tests::j (mrjam-log::lire-demande-mcp c cookies id) "client")))
      ;; Même retour exact, nouveau consentement requis, nouveau code PKCE.
      (let* ((url (mrjam-log::consentir-mcp c cookies id t))
             (parametres (mrjam-metier::decode-query (subseq url (1+ (position #\? url)))))
             (jetons (mrjam-log::jetons-mcp c
                       (vision:jobject "client_id" (make-string 32 :initial-element #\A)
                         "grant_type" "authorization_code" "redirect_uri" "https://client.example.test/callback"
                         "code" (mrjam-log-kanidm-tests::j parametres "code") "code_verifier" v))))
        (assert (equal "alice" (mrjam-log::verifier-mcp c
                   (concatenate 'string "Bearer " (mrjam-log-kanidm-tests::j jetons "access_token")))))))
    (setf (cdr (assoc "client_id" (vision:json-object-entries q) :test #'equal)) "client-inconnu")
    (assert (handler-case (progn (mrjam-log::demander-mcp c cookies q) nil)
              (mrjam-log:log-error (e) (= 400 (mrjam-log:statut-erreur e)))))))
