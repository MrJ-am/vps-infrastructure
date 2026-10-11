(in-package #:mrjam-native)

(defun decimal-court (nombre)
  "ECMAScript Number::toString : minimum de chiffres, candidat le plus proche,
ties vers le pair. Recherche décimale sur la valeur rationnelle binaire64 exacte."
  (let* ((exact (rational nombre))
         (exposant (floor (log nombre 10d0))))
    ;; LOG sert seulement d'estimation ; frontières de puissances contrôlées exactement.
    (loop while (< exact (expt 10 exposant)) do (decf exposant))
    (loop while (>= exact (expt 10 (1+ exposant))) do (incf exposant))
    (loop for k from 1 to 17
          for puissance = (- exposant k -1)
          for facteur = (expt 10 puissance)
          for significande = (round (/ exact facteur))
          when (handler-case (= nombre (sb-int:with-float-traps-masked (:underflow)
                                          (coerce (* significande facteur) 'double-float)))
                 (floating-point-overflow () nil))
            do (let* ((digits (write-to-string significande))
                      (decimal (+ (length digits) puissance)))
                 (return-from decimal-court (values (string-right-trim "0" digits) decimal))))
    (echec-natif :conversion-decimale)))

(defun nombre-js (nombre)
  "Émission décimale compatible JSON.stringify sur le domaine des sauvegardes."
  (let ((n (coerce nombre 'double-float)))
    (when (or (sb-ext:float-nan-p n) (sb-ext:float-infinity-p n))
      (echec-natif :nombre-json-non-fini))
    (when (zerop n) (return-from nombre-js "0"))
    (multiple-value-bind (digits decimal) (decimal-court (abs n))
      (with-output-to-string (s)
        (when (minusp n) (write-char #\- s))
        (cond
          ((and (< -6 decimal) (<= decimal 21))
           (cond ((<= decimal 0) (write-string "0." s)
                  (loop repeat (- decimal) do (write-char #\0 s)) (write-string digits s))
                 ((>= decimal (length digits)) (write-string digits s)
                  (loop repeat (- decimal (length digits)) do (write-char #\0 s)))
                 (t (write-string digits s :end decimal) (write-char #\. s)
                    (write-string digits s :start decimal))))
          (t (write-char (char digits 0) s)
             (when (> (length digits) 1) (write-char #\. s) (write-string digits s :start 1))
             (format s "e~A~D" (if (>= decimal 1) "+" "") (1- decimal))))))))

(defun indice-js (cle)
  (and (stringp cle) (<= 1 (length cle) 10)
       (or (= (length cle) 1) (char/= (char cle 0) #\0))
       (every (lambda (c) (char<= #\0 c #\9)) cle)
       (let ((n (parse-integer cle))) (and (< n #xffffffff) n))))

(defun json-js (objet)
  "Empreinte historique : ordre des propriétés ECMAScript, Unicode, nombres binaires64.
Ce n'est pas une sérialisation canonique indépendante du contrat Node."
  (labels ((emit (v s)
             (cond
               ((numberp v) (write-string (nombre-js v) s))
               ((stringp v)
                (write-char #\" s)
                ;; JSON.stringify émet les échappements hexadécimaux en minuscules.
                (loop for c across v do
                  (if (< (char-code c) 32)
                      (case c (#\Backspace (write-string "\\b" s))
                              (#\Page (write-string "\\f" s))
                              (#\Newline (write-string "\\n" s))
                              (#\Return (write-string "\\r" s))
                              (#\Tab (write-string "\\t" s))
                              (t (write-string (string-downcase (format nil "\\u~4,'0X" (char-code c))) s)))
                      (case c (#\" (write-string "\\\"" s))
                              (#\\ (write-string "\\\\" s))
                              (t (write-char c s)))))
                (write-char #\" s))
               ((vision:json-object-p v)
                (write-char #\{ s)
                (let* ((entries (vision:json-object-entries v))
                       (indices (remove-if-not (lambda (p) (indice-js (car p))) entries))
                       (autres (remove-if (lambda (p) (indice-js (car p))) entries)))
                  (loop for (cle . valeur) in (append (sort (copy-list indices) #'< :key (lambda (p) (indice-js (car p)))) autres)
                        for premier = t then nil do
                          (unless premier (write-char #\, s)) (emit cle s)
                          (write-char #\: s) (emit valeur s)))
                (write-char #\} s))
               ((vision:json-array-p v)
                (write-char #\[ s)
                (loop for valeur in (vision:json-array-items v) for premier = t then nil do
                  (unless premier (write-char #\, s)) (emit valeur s)) (write-char #\] s))
               (t (write-string (vision:json-encode v) s)))))
    (with-output-to-string (s) (emit objet s))))
