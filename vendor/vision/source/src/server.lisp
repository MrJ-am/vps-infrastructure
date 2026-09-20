(in-package #:vision)

(defconstant +maximum-request-line-length+ 4096)
(defconstant +maximum-header-line-length+ 8192)
(defconstant +maximum-header-lines+ 64)
(defconstant +maximum-body-length+ 65536)
(defconstant +request-timeout-seconds+ 10)

(defparameter *document-root* "docs/")

(define-condition http-error (error)
  ((status :initarg :status :reader http-error-status)
   (reason :initarg :reason :reader http-error-reason)
   (message :initarg :message :reader http-error-message)))

(defun fail-request (status reason message)
  (error 'http-error :status status :reason reason :message message))

(defun environment-value (name default)
  (or (sb-ext:posix-getenv name) default))

(defun trim-http-line (line)
  (string-right-trim '(#\Return #\Linefeed) line))

(defun safe-read-line (stream maximum-length description &key (eof-error-p t))
  (let ((raw-line (read-line stream nil nil)))
    (when (and eof-error-p (null raw-line))
      (fail-request 400 "Bad Request" (format nil "Missing ~A." description)))
    (when (and raw-line (> (length raw-line) maximum-length))
      (fail-request 431 "Request Header Fields Too Large"
                    (format nil "~A is too long." description)))
    (and raw-line (trim-http-line raw-line))))

(defun split-on-spaces (text)
  (labels ((collect-parts (start parts)
             (let ((word-start (position-if-not
                                (lambda (character) (char= character #\Space))
                                text :start start)))
               (if (null word-start)
                   (nreverse parts)
                   (let ((word-end (or (position #\Space text :start word-start)
                                       (length text))))
                     (collect-parts word-end
                                    (cons (subseq text word-start word-end)
                                          parts)))))))
    (collect-parts 0 '())))

(defun http-token-character-p (character)
  (or (alphanumericp character)
      (find character "!#$%&'*+-.^_`|~" :test #'char=)))

(defun valid-header-value-p (value)
  (every (lambda (character)
           (or (char= character #\Tab)
               (<= 32 (char-code character) 126)))
         value))

(defun read-request-line (stream)
  (let* ((line (safe-read-line stream +maximum-request-line-length+
                               "request line"))
         (parts (split-on-spaces line)))
    (unless (= (length parts) 3)
      (fail-request 400 "Bad Request" "Malformed request line."))
    (destructuring-bind (method target version) parts
      (unless (member method '("GET" "POST") :test #'string=)
        (fail-request 405 "Method Not Allowed" "Only GET and POST are supported."))
      (unless (and (> (length target) 0) (char= (char target 0) #\/))
        (fail-request 400 "Bad Request" "Only origin-form request targets are accepted."))
      (unless (member version '("HTTP/1.0" "HTTP/1.1") :test #'string=)
        (fail-request 505 "HTTP Version Not Supported"
                      "Only HTTP/1.0 and HTTP/1.1 are supported."))
      (values method target version))))

(defun read-headers (stream)
  (loop with headers = '()
        for count from 1
        for line = (safe-read-line stream +maximum-header-line-length+
                                   "header line")
        do (when (> count +maximum-header-lines+)
             (fail-request 431 "Request Header Fields Too Large"
                           "Too many request headers."))
           (when (string= line "")
             (return (nreverse headers)))
           (let ((separator (position #\: line)))
             (unless (and separator (> separator 0))
               (fail-request 400 "Bad Request" "Malformed request header."))
             (let ((name (subseq line 0 separator))
                   (value (string-trim '(#\Space #\Tab)
                                       (subseq line (1+ separator)))))
               (unless (every #'http-token-character-p name)
                 (fail-request 400 "Bad Request" "Invalid request header name."))
               (unless (valid-header-value-p value)
                 (fail-request 400 "Bad Request" "Invalid request header value."))
               (push (cons (string-downcase name) value) headers)))
        finally (return (nreverse headers))))

(defun header-values (name headers)
  (loop for (header-name . value) in headers
        when (string= header-name name)
          collect value))

(defun request-content-length (headers)
  (let ((values (header-values "content-length" headers)))
    (when (> (length values) 1)
      (fail-request 400 "Bad Request" "Multiple Content-Length headers are forbidden."))
    (if values
        (handler-case
            (let ((length (parse-integer (first values) :junk-allowed nil)))
              (when (minusp length)
                (fail-request 400 "Bad Request" "Negative Content-Length."))
              (when (> length +maximum-body-length+)
                (fail-request 413 "Content Too Large" "Request body is too large."))
              length)
          (parse-error ()
            (fail-request 400 "Bad Request" "Invalid Content-Length.")))
        0)))

(defun validate-transfer-encoding (headers)
  (when (header-values "transfer-encoding" headers)
    (fail-request 400 "Bad Request" "Transfer-Encoding is not accepted.")))

(defun request-path (target)
  (let ((query-start (position #\? target)))
    (when query-start
      (fail-request 400 "Bad Request" "Query strings are not accepted by this API."))
    target))

(defun utf-8-length (text)
  (length (sb-ext:string-to-octets text :external-format :utf-8)))

(defun write-response (stream status reason body content-type &key headers)
  (format stream "HTTP/1.1 ~D ~A~C~C" status reason #\Return #\Linefeed)
  (format stream "Content-Type: ~A~C~C" content-type #\Return #\Linefeed)
  (format stream "Content-Length: ~D~C~C" (utf-8-length body)
          #\Return #\Linefeed)
  (format stream "Connection: close~C~C" #\Return #\Linefeed)
  (format stream "X-Content-Type-Options: nosniff~C~C" #\Return #\Linefeed)
  (format stream "Referrer-Policy: no-referrer~C~C" #\Return #\Linefeed)
  (dolist (header headers)
    (format stream "~A: ~A~C~C" (car header) (cdr header)
            #\Return #\Linefeed))
  (format stream "~C~C~A" #\Return #\Linefeed body)
  (finish-output stream))

(defun json-string (text)
  (format nil "\"~A\"" (json-escape text)))

(defun write-json (stream status reason body &key headers)
  (write-response stream status reason body "application/json; charset=utf-8"
                  :headers (append headers
                                   '(("Cache-Control" . "no-store")))))

(defun slurp-document (filename)
  (let ((path (merge-pathnames filename
                               (pathname (format nil "~A/" *document-root*)))))
    (handler-case
        (with-open-file (input path :direction :input :external-format :utf-8)
          (with-output-to-string (output)
            (loop for line = (read-line input nil nil)
                  while line
                  do (write-line line output))))
      (file-error ()
        (fail-request 503 "Service Unavailable"
                      "API documentation is temporarily unavailable.")))))

(defun authenticated-request-p (headers)
  (equal (header-values "x-vision-authenticated" headers) '("1")))

(defun api-path-p (path)
  (and (>= (length path) 5)
       (string= path "/api/" :end1 5 :end2 5)))

(defun protected-path-p (path)
  (or (api-path-p path) (string= path "/mcp")))

(defun json-content-type-p (headers)
  (let ((values (header-values "content-type" headers)))
    (and (= (length values) 1)
         (let* ((value (string-downcase (first values)))
                (separator (position #\; value))
                (media-type (string-trim '(#\Space #\Tab)
                                         (if separator
                                             (subseq value 0 separator)
                                             value))))
           (string= media-type "application/json")))))

(defun read-request-body (stream content-length)
  (with-output-to-string (output)
    (loop with consumed = 0
          while (< consumed content-length)
          for character = (read-char stream nil nil)
          do (unless character
               (fail-request 400 "Bad Request" "Request body ended prematurely."))
             (let ((width (utf-8-length (string character))))
               (when (> (+ consumed width) content-length)
                 (fail-request 400 "Bad Request" "Content-Length splits a UTF-8 character."))
               (incf consumed width)
               (write-char character output)))))

(defun write-empty-response (stream status reason &key headers)
  (format stream "HTTP/1.1 ~D ~A~C~C" status reason #\Return #\Linefeed)
  (format stream "Content-Length: 0~C~C" #\Return #\Linefeed)
  (format stream "Connection: close~C~C" #\Return #\Linefeed)
  (format stream "X-Content-Type-Options: nosniff~C~C" #\Return #\Linefeed)
  (dolist (header headers)
    (format stream "~A: ~A~C~C" (car header) (cdr header)
            #\Return #\Linefeed))
  (format stream "~C~C" #\Return #\Linefeed)
  (finish-output stream))

(defun write-authentication-required (stream)
  (write-json stream 401 "Unauthorized"
              "{\"error\":\"authentication_required\",\"message\":\"HTTP Basic authentication is required.\"}"
              :headers '(("WWW-Authenticate" . "Basic realm=\"Vision API\", charset=\"UTF-8\""))))

(defun route-request (stream method path headers body)
  (when (and (protected-path-p path) (not (authenticated-request-p headers)))
    (write-authentication-required stream)
    (return-from route-request))
  (cond
    ((and (string= method "GET") (string= path "/"))
     (write-response stream 308 "Permanent Redirect" "" "text/plain; charset=utf-8"
                     :headers '(("Location" . "/docs")
                                ("Cache-Control" . "no-store"))))
    ((and (string= method "GET")
          (member path '("/docs" "/docs/") :test #'string=))
     (write-response stream 200 "OK" (slurp-document "index.html")
                     "text/html; charset=utf-8"
                     :headers '(("Cache-Control" . "public, max-age=300")
                                ("Content-Security-Policy" . "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'"))))
    ((and (string= method "GET") (string= path "/privacy"))
     (write-response stream 200 "OK" (slurp-document "privacy.html")
                     "text/html; charset=utf-8"
                     :headers '(("Cache-Control" . "public, max-age=300")
                                ("Content-Security-Policy" . "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'"))))
    ((and (string= method "GET") (string= path "/openapi.json"))
     (write-response stream 200 "OK" (slurp-document "openapi.json")
                     "application/json; charset=utf-8"
                     :headers '(("Cache-Control" . "public, max-age=300"))))
    ((and (string= method "GET")
          (string= path "/mobile-live-test-openapi.json"))
     (write-response stream 200 "OK"
                     (slurp-document "mobile-live-test-openapi.json")
                     "application/json; charset=utf-8"
                     :headers '(("Cache-Control" . "public, max-age=300"))))
    ((and (string= method "GET") (string= path "/healthz"))
     (write-json stream 200 "OK"
                 (format nil "{\"status\":\"ok\",\"version\":~A}"
                         (json-string *version*))))
    ((and (string= method "GET") (string= path "/api/v1/health"))
     (write-json stream 200 "OK"
                 (format nil "{\"status\":\"ok\",\"version\":~A}"
                         (json-string *version*))))
    ((and (string= method "GET") (string= path "/api/v1/capabilities"))
     (write-json stream 200 "OK"
                 (format nil
                         "{\"api\":\"vision\",\"version\":~A,\"operations\":[\"getVisionHealth\",\"getVisionCapabilities\",\"sayHello\"]}"
                         (json-string *version*))))
    ((and (string= method "GET") (string= path "/mcp"))
     (write-json stream 405 "Method Not Allowed"
                 "{\"error\":\"method_not_allowed\",\"message\":\"Use POST for the stateless MCP endpoint.\"}"
                 :headers '(("Allow" . "POST"))))
    ((and (string= method "POST") (string= path "/mcp"))
     (if (not (json-content-type-p headers))
         (write-json stream 415 "Unsupported Media Type"
                     "{\"error\":\"unsupported_media_type\",\"message\":\"MCP requests require application/json.\"}")
         (multiple-value-bind (status reason response-body)
             (handle-mcp-message body)
           (if response-body
               (write-json stream status reason response-body)
               (write-empty-response stream status reason
                                     :headers '(("Cache-Control" . "no-store")))))))
    ((and (string= method "GET")
          (string= path "/api/v1/mobile-live-test"))
     (write-json stream 200 "OK"
                 "{\"ok\":true,\"proof\":\"VISION-MOBILE-LIVE-AUTH-OK\",\"scope\":\"test-only\",\"message\":\"HTTP Basic authentication succeeded. No Vision data was accessed.\"}"))
    ((and (string= method "POST") (string= path "/api/v1/hello"))
     (if (zerop (length body))
         (write-json stream 200 "OK" "{\"message\":\"World\"}")
         (write-json stream 415 "Unsupported Media Type"
                     "{\"error\":\"body_not_supported\",\"message\":\"This operation takes no request body.\"}")))
    ((api-path-p path)
     (write-json stream 404 "Not Found"
                 "{\"error\":\"not_found\",\"message\":\"Unknown API operation.\"}"))
    (t
     (write-json stream 404 "Not Found"
                 "{\"error\":\"not_found\",\"message\":\"Resource not found.\"}"))))

(defun handle-request (stream)
  (multiple-value-bind (method target version) (read-request-line stream)
    (declare (ignore version))
    (let ((headers (read-headers stream)))
      (validate-transfer-encoding headers)
      (let ((content-length (request-content-length headers)))
        (when (and (> content-length 0) (string= method "GET"))
          (fail-request 400 "Bad Request" "GET requests must not contain a body."))
        (route-request stream method (request-path target) headers
                       (read-request-body stream content-length))))))

(defun handle-client (client)
  (let ((stream (sb-bsd-sockets:socket-make-stream
                 client
                 :input t
                 :output t
                 :element-type 'character
                 :external-format :utf-8
                 :buffering :full
                 :auto-close t)))
    (unwind-protect
         (handler-case
             (sb-ext:with-timeout +request-timeout-seconds+
               (handle-request stream))
           (http-error (condition)
             (write-json stream
                         (http-error-status condition)
                         (http-error-reason condition)
                         (format nil "{\"error\":\"invalid_request\",\"message\":~A}"
                                 (json-string (http-error-message condition)))))
           (sb-ext:timeout ()
             (write-json stream 408 "Request Timeout"
                         "{\"error\":\"request_timeout\",\"message\":\"The request took too long.\"}"))
           (error (condition)
             (format *error-output* "Request failed: ~A~%" condition)
             (finish-output *error-output*)
             (ignore-errors
               (write-json stream 500 "Internal Server Error"
                           "{\"error\":\"internal_error\",\"message\":\"Unexpected server error.\"}"))))
      (ignore-errors (close stream)))))

(defun make-listener (host port)
  (let ((socket (make-instance 'sb-bsd-sockets:inet-socket
                               :type :stream
                               :protocol :tcp)))
    (setf (sb-bsd-sockets:sockopt-reuse-address socket) t)
    (sb-bsd-sockets:socket-bind socket
                                (sb-bsd-sockets:make-inet-address host)
                                port)
    (sb-bsd-sockets:socket-listen socket 128)
    socket))

(defun dispatch-client (client)
  (handler-case
      (sb-thread:make-thread
       (lambda () (handle-client client))
       :name "vision-http-client")
    (error (condition)
      ;; Une saturation transitoire ne doit pas arrêter le processus principal.
      (format *error-output* "Client rejected: ~A~%" condition)
      (finish-output *error-output*)
      (ignore-errors (sb-bsd-sockets:socket-close client)))))

(defun serve (&key (host "127.0.0.1") (port 3001))
  (let ((listener (make-listener host port)))
    (format t "vision ~A listening on http://~A:~D/~%" *version* host port)
    (finish-output)
    (unwind-protect
         (loop
           (let ((client (sb-bsd-sockets:socket-accept listener)))
             (dispatch-client client)))
      (sb-bsd-sockets:socket-close listener))))

(defun main ()
  (setf *version* (environment-value "VISION_VERSION" "1.1.1")
        *document-root* (environment-value "VISION_DOCUMENT_ROOT" "docs/"))
  (handler-case
      (serve :host (environment-value "IP" "127.0.0.1")
             :port (parse-integer
                    (environment-value "PORT" "3001")
                    :junk-allowed nil))
    (error (condition)
      (format *error-output* "Fatal error: ~A~%" condition)
      (finish-output *error-output*)
      (sb-ext:exit :code 1))))
