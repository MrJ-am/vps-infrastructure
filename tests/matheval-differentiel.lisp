(defpackage #:matheval-differentiel (:use #:cl) (:export #:verifier))
(in-package #:matheval-differentiel)

(defun egal (a b)
  (cond ((and (numberp a) (numberp b)) (< (abs (- a b)) 1d-10))
        ((and (vision:json-object-p a) (vision:json-object-p b))
         (and (= (length (vision:json-object-entries a)) (length (vision:json-object-entries b)))
              (every (lambda (p)
                       (multiple-value-bind (v present) (vision:json-object-get b (car p))
                         (and present (egal (cdr p) v))))
                     (vision:json-object-entries a))))
        ((and (vision:json-array-p a) (vision:json-array-p b))
         (and (= (length (vision:json-array-items a)) (length (vision:json-array-items b)))
              (every #'egal (vision:json-array-items a) (vision:json-array-items b))))
        (t (equal a b))))

(defun verifier (cas corpus)
  (let ((bank (vision:parse-json (uiop:read-file-string corpus))))
    (loop for c in (vision:json-array-items (vision:parse-json (uiop:read-file-string cas)))
          for numero from 1 do
      (let* ((op (vision:json-object-get c "op"))
             (resultat
               (cond
                 ((equal op "random")
                  (let ((r (matheval:generateur-32 (vision:json-object-get c "seed"))))
                    (vision:%make-json-array (loop repeat 1000 collect (funcall r)))))
                 ((equal op "session")
                  (vision:%make-json-array
                    (loop for q in (matheval:preparer-session bank
                                     (vision:json-array-items (vision:json-object-get c "levels"))
                                     (vision:json-object-get c "seed")) collect
                          (vision:jobject "id" (vision:json-object-get q "id")
                            "productions" (vision:%make-json-array
                              (mapcar (lambda (p) (vision:json-object-get p "id"))
                                (vision:json-array-items (vision:json-object-get q "productions"))))))))
                 ((equal op "summary") (matheval:resume (vision:json-array-items (vision:json-object-get c "values"))))
                 ((equal op "answers") (matheval:resumer-reponses (vision:json-array-items (vision:json-object-get c "rows"))))
                 ((equal op "csv") (matheval:export-csv (vision:json-array-items (vision:json-object-get c "rows"))))
                 ((member op '("participation" "checkpoint") :test #'equal)
                  (handler-case
                    (funcall (if (equal op "participation") #'matheval:valider-participation #'matheval:valider-sauvegarde)
                             (vision:json-object-get c "data"))
                    (matheval:validation-error () (vision:jobject "refus" :true))))
                 ((equal op "rattachements")
                  (handler-case
                    (progn (matheval:valider-rattachements (vision:json-object-get c "data")
                             (vision:jobject "question_order" (vision:json-object-get c "order")) bank) :true)
                    (matheval:validation-error () :false)))
                 (t (error "Opération de fixture inconnue.")))))
        (unless (egal resultat (vision:json-object-get c "expected"))
          (error "Différence cas ~D pour ~A : ~A" numero op (vision:json-encode resultat))))))
  (format t "Référence différentielle JS/Lisp réussie.~%") t)
