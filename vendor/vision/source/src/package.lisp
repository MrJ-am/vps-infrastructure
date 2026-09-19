(require :sb-bsd-sockets)

(defpackage #:vision
  (:use #:cl)
  (:export #:main
           #:serve))
