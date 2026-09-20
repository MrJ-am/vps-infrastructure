(in-package #:vision)

;;; This scheduler is a native Common Lisp port of the scalar FSRS-6
;;; implementation published by Open Spaced Repetition in fsrs-rs v6.6.2.
;;; Upstream commit: 6088949b99d44f46f5328fd7289d209b9a842b68
;;; License: BSD-3-Clause. See THIRD_PARTY_NOTICES.md.

(defparameter +fsrs-model-version+ "fsrs-6")
(defparameter +fsrs-implementation-version+ "fsrs-rs-6.6.2")
(defparameter +fsrs-upstream-commit+
  "6088949b99d44f46f5328fd7289d209b9a842b68")

(defparameter +fsrs-default-parameters+
  #(0.212d0 1.2931d0 2.3065d0 8.2956d0 6.4133d0 0.8334d0 3.0194d0
    0.001d0 1.8722d0 0.1666d0 0.796d0 1.4835d0 0.0614d0 0.2629d0
    1.6483d0 0.6014d0 1.8729d0 0.5425d0 0.0912d0 0.0658d0 0.1542d0))

(defconstant +fsrs-stability-minimum+ 0.001d0)
(defconstant +fsrs-stability-maximum+ 36500.0d0)
(defconstant +fsrs-difficulty-minimum+ 1.0d0)
(defconstant +fsrs-difficulty-maximum+ 10.0d0)
(defconstant +fsrs-maximum-interval-days+ 36500)

(defstruct (fsrs-memory-state
             (:constructor make-fsrs-memory-state (stability difficulty)))
  (stability 0.0d0 :type double-float)
  (difficulty 0.0d0 :type double-float))

(defun fsrs-clamp (value minimum maximum)
  (min maximum (max minimum value)))

(defun fsrs-finite-number-p (value)
  (and (realp value)
       (let ((number (coerce value 'double-float)))
         (not (or (sb-ext:float-infinity-p number)
                  (sb-ext:float-nan-p number))))))

(defun validate-fsrs-parameters (parameters)
  (unless (and (vectorp parameters)
               (= (length parameters) 21)
               (loop for value across parameters always (fsrs-finite-number-p value)))
    (error "FSRS-6 requires exactly 21 finite parameters."))
  (map 'vector (lambda (value) (coerce value 'double-float)) parameters))

(defun fsrs-json-parameters (value)
  (unless (and (json-array-p value)
               (= (length (json-array-items value)) 21))
    (database-fail "Invalid FSRS settings."
                   "The database must provide 21 FSRS-6 parameters."))
  (handler-case
      (validate-fsrs-parameters
       (coerce (json-array-items value) 'vector))
    (error (condition)
      (database-fail "Invalid FSRS settings." (princ-to-string condition)))))

(defun fsrs-initial-stability (parameters rating)
  (aref parameters (1- rating)))

(defun fsrs-initial-difficulty (parameters rating)
  (+ (aref parameters 4)
     (- (exp (* (aref parameters 5) (1- rating))))
     1.0d0))

(defun fsrs-retrievability (stability elapsed-days parameters)
  (let* ((stability (max +fsrs-stability-minimum+
                         (coerce stability 'double-float)))
         (elapsed-days (max 0.0d0 (coerce elapsed-days 'double-float)))
         (decay (- (aref parameters 20)))
         (factor (- (exp (/ (log 0.9d0) decay)) 1.0d0)))
    (expt (+ (* (/ elapsed-days stability) factor) 1.0d0) decay)))

(defun fsrs-next-interval (stability desired-retention parameters)
  (unless (and (realp desired-retention)
               (< 0.0d0 (coerce desired-retention 'double-float) 1.0d0))
    (error "Desired retention must be strictly between zero and one."))
  (let* ((stability (max +fsrs-stability-minimum+
                         (coerce stability 'double-float)))
         (retention (coerce desired-retention 'double-float))
         (decay (- (aref parameters 20)))
         (factor (- (exp (/ (log 0.9d0) decay)) 1.0d0)))
    (/ (* stability (- (expt retention (/ 1.0d0 decay)) 1.0d0))
       factor)))

(defun fsrs-mean-reversion (parameters new-difficulty)
  (+ (* (aref parameters 7)
        (- (fsrs-initial-difficulty parameters 4) new-difficulty))
     new-difficulty))

(defun fsrs-next-difficulty (parameters difficulty rating)
  (let* ((delta (* (- (aref parameters 6)) (- rating 3.0d0)))
         (damped (/ (* (- 10.0d0 difficulty) delta) 9.0d0)))
    (fsrs-clamp
     (fsrs-mean-reversion parameters (+ difficulty damped))
     +fsrs-difficulty-minimum+
     +fsrs-difficulty-maximum+)))

(defun fsrs-stability-after-success
    (parameters stability difficulty retrievability rating)
  (let ((hard-penalty (if (= rating 2) (aref parameters 15) 1.0d0))
        (easy-bonus (if (= rating 4) (aref parameters 16) 1.0d0)))
    (* stability
       (+ (* (exp (aref parameters 8))
             (- 11.0d0 difficulty)
             (expt stability (- (aref parameters 9)))
             (- (exp (* (- 1.0d0 retrievability)
                        (aref parameters 10)))
                1.0d0)
             hard-penalty
             easy-bonus)
          1.0d0))))

(defun fsrs-stability-after-failure
    (parameters stability difficulty retrievability)
  (let ((new-stability
          (* (aref parameters 11)
             (expt difficulty (- (aref parameters 12)))
             (- (expt (+ stability 1.0d0) (aref parameters 13)) 1.0d0)
             (exp (* (- 1.0d0 retrievability) (aref parameters 14)))))
        (upper-bound
          (/ stability (exp (* (aref parameters 17)
                               (aref parameters 18))))))
    (min new-stability upper-bound)))

(defun fsrs-short-term-stability (parameters stability rating)
  (let* ((increase
           (* (exp (* (aref parameters 17)
                      (+ (- rating 3.0d0) (aref parameters 18))))
              (expt stability (- (aref parameters 19)))))
         (bounded-increase (if (>= rating 2) (max 1.0d0 increase) increase)))
    (* stability bounded-increase)))

(defun fsrs-next-state (state rating elapsed-days parameters)
  (unless (and (integerp rating) (<= 1 rating 4))
    (error "FSRS rating must be an integer between 1 and 4."))
  (setf parameters (validate-fsrs-parameters parameters))
  (if (null state)
      (make-fsrs-memory-state
       (fsrs-clamp (fsrs-initial-stability parameters rating)
                   +fsrs-stability-minimum+ +fsrs-stability-maximum+)
       (fsrs-clamp (fsrs-initial-difficulty parameters rating)
                   +fsrs-difficulty-minimum+ +fsrs-difficulty-maximum+))
      (let* ((stability
               (fsrs-clamp (fsrs-memory-state-stability state)
                           +fsrs-stability-minimum+ +fsrs-stability-maximum+))
             (difficulty
               (fsrs-clamp (fsrs-memory-state-difficulty state)
                           +fsrs-difficulty-minimum+ +fsrs-difficulty-maximum+))
             (elapsed (max 0.0d0 (coerce elapsed-days 'double-float)))
             (retrievability
               (fsrs-retrievability stability elapsed parameters))
             (new-stability
               (cond
                 ((zerop elapsed)
                  (fsrs-short-term-stability parameters stability rating))
                 ((= rating 1)
                  (fsrs-stability-after-failure
                   parameters stability difficulty retrievability))
                 (t
                  (fsrs-stability-after-success
                   parameters stability difficulty retrievability rating)))))
        (make-fsrs-memory-state
         (fsrs-clamp new-stability
                     +fsrs-stability-minimum+ +fsrs-stability-maximum+)
         (fsrs-next-difficulty parameters difficulty rating)))))

(defun fsrs-round-positive (value)
  ;; Rust's f32::round rounds positive half values away from zero, unlike
  ;; Common Lisp ROUND, which rounds ties to an even integer.
  (floor (+ (coerce value 'double-float) 0.5d0)))

(defun fsrs-schedule (state rating elapsed-days desired-retention parameters)
  (let* ((next-state
           (fsrs-next-state state rating elapsed-days parameters))
         (interval
           (fsrs-next-interval
            (fsrs-memory-state-stability next-state)
            desired-retention
            parameters))
         (scheduled-days
           (fsrs-clamp (fsrs-round-positive interval)
                       1 +fsrs-maximum-interval-days+)))
    (values next-state interval scheduled-days)))
