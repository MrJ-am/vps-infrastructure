(require :sb-bsd-sockets)

(defpackage #:vision
  (:use #:cl)
  (:export #:main
           #:serve))

(in-package #:vision)

(defparameter *version* "1.3.0")
