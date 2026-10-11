(in-package #:mrjam-native)

;; Pas d'ouverture de DSO lors du chargement ASDF. Le cycle de vie central fournit
;; le chemin absolu du libcrypto verrouillé dans sa closure ; les tests aussi.
(defun initialiser-crypto (chemin)
  (unless (and (uiop:absolute-pathname-p chemin) (probe-file chemin))
    (echec-natif :chemin-libcrypto))
  (sb-alien:load-shared-object (namestring (truename chemin))))

(sb-alien:define-alien-routine ("EVP_Q_digest" %digest) sb-alien:int
  (ctx sb-alien:system-area-pointer) (nom sb-alien:c-string)
  (proprietes sb-alien:system-area-pointer) (donnees sb-alien:system-area-pointer)
  (taille sb-alien:unsigned-long) (sortie sb-alien:system-area-pointer)
  (taille-sortie (* sb-alien:unsigned-long)))

(sb-alien:define-alien-routine ("RAND_bytes" %random) sb-alien:int
  (sortie sb-alien:system-area-pointer) (taille sb-alien:int))

(sb-alien:define-alien-routine ("CRYPTO_memcmp" %memcmp) sb-alien:int
  (a sb-alien:system-area-pointer) (b sb-alien:system-area-pointer)
  (taille sb-alien:unsigned-long))

(sb-alien:define-alien-routine ("EVP_PBE_scrypt" %scrypt) sb-alien:int
  (mot sb-alien:system-area-pointer) (taille-mot sb-alien:unsigned-long)
  (sel sb-alien:system-area-pointer) (taille-sel sb-alien:unsigned-long)
  (n sb-alien:unsigned-long) (r sb-alien:unsigned-long) (p sb-alien:unsigned-long)
  (maxmem sb-alien:unsigned-long) (sortie sb-alien:system-area-pointer)
  (taille-sortie sb-alien:unsigned-long))

(defun octets (texte)
  (sb-ext:string-to-octets texte :external-format :utf-8 :null-terminate nil))

(defun hex (donnees)
  (let ((alphabet "0123456789abcdef"))
    (with-output-to-string (s)
      (loop for b across donnees do (write-char (char alphabet (ash b -4)) s)
                                   (write-char (char alphabet (logand b 15)) s)))))

(defun dehex (texte)
  (unless (and (stringp texte) (evenp (length texte))
               (every (lambda (c) (digit-char-p c 16)) texte))
    (return-from dehex nil))
  (let ((out (make-array (/ (length texte) 2) :element-type '(unsigned-byte 8))))
    (loop for i below (length out) do
      (setf (aref out i) (+ (* 16 (digit-char-p (char texte (* i 2)) 16))
                           (digit-char-p (char texte (1+ (* i 2))) 16)))) out))

(defun digest-octets (donnees)
  (let ((out (make-array 32 :element-type '(unsigned-byte 8))))
    (sb-alien:with-alien ((taille sb-alien:unsigned-long 0))
      (sb-sys:with-pinned-objects (donnees out)
        (unless (and (= 1 (%digest (sb-sys:int-sap 0) "SHA256" (sb-sys:int-sap 0)
                                  (sb-sys:vector-sap donnees) (length donnees)
                                  (sb-sys:vector-sap out) (sb-alien:addr taille)))
                     (= taille 32)) (echec-natif :sha256)))) out))

(defun sha256 (texte) (hex (digest-octets (octets texte))))

(defun aleatoire-hex (&optional (taille 32))
  (unless (<= 1 taille 1024) (echec-natif :taille-aleatoire))
  (let ((out (make-array taille :element-type '(unsigned-byte 8))))
    (unwind-protect
        (progn (sb-sys:with-pinned-objects (out)
                 (unless (= 1 (%random (sb-sys:vector-sap out) taille))
                   (echec-natif :random))) (hex out))
      (fill out 0))))

(defun octets-egaux-p (a b)
  (and (= (length a) (length b))
       (sb-sys:with-pinned-objects (a b)
         (zerop (%memcmp (sb-sys:vector-sap a) (sb-sys:vector-sap b) (length a))))))

(defun secret-egal-p (a b)
  ;; Même contrat que sameSecret Node : comparaison de SHA256 de longueur fixe.
  (and (stringp a) (stringp b)
       (octets-egaux-p (digest-octets (octets a)) (digest-octets (octets b)))))

(defun scrypt (mot sel)
  "Paramètres historiques Matheval : sel UTF-8 (hex textuel), N=131072/r=8/p=1."
  (let ((mot-octets (octets mot)) (sel-octets (octets sel))
        (out (make-array 64 :element-type '(unsigned-byte 8))))
    (unwind-protect
        (progn
          (sb-sys:with-pinned-objects (mot-octets sel-octets out)
            (unless (= 1 (%scrypt (sb-sys:vector-sap mot-octets) (length mot-octets)
                                   (sb-sys:vector-sap sel-octets) (length sel-octets)
                                   131072 8 1 (* 256 1024 1024)
                                   (sb-sys:vector-sap out) 64)) (echec-natif :scrypt)))
          (hex out))
      (fill mot-octets 0) (fill out 0))))

(defun mot-de-passe-encoder (mot)
  (let ((sel (aleatoire-hex 16)))
    (format nil "scrypt:~A:~A" sel (scrypt mot sel))))

(defun mot-de-passe-verifier (mot empreinte)
  (let ((parts (and (stringp empreinte) (uiop:split-string empreinte :separator ":"))))
    (unless (and (= (length parts) 3) (string= (first parts) "scrypt")
                 (= (length (second parts)) 32) (dehex (second parts))
                 (= (length (third parts)) 128) (dehex (third parts)))
      (return-from mot-de-passe-verifier nil))
    (octets-egaux-p (dehex (scrypt mot (second parts))) (dehex (third parts)))))
