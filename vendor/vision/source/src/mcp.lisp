(in-package #:vision)

(defparameter +mcp-default-protocol-version+ "2025-06-18")

(define-condition invalid-parameters (error)
  ((message :initarg :message :reader invalid-parameters-message)))

(defun invalid-parameters (message &rest arguments)
  (error 'invalid-parameters :message (apply #'format nil message arguments)))

(defun object-schema (properties &rest required)
  (jobject "type" "object"
           "properties" properties
           "required" (%make-json-array required)
           "additionalProperties" :false))

(defun array-schema (items &key (maximum 50))
  (jobject "type" "array" "items" items "maxItems" maximum))

(defun string-schema (&key description maximum-length enum nullable)
  (apply #'jobject
         (append
          (list "type" (if nullable (jarray "string" "null") "string"))
          (when description (list "description" description))
          (when maximum-length (list "maxLength" maximum-length))
          (when enum (list "enum" (%make-json-array enum))))))

(defun integer-schema (&key description minimum maximum default)
  (apply #'jobject
         (append (list "type" "integer")
                 (when description (list "description" description))
                 (when minimum (list "minimum" minimum))
                 (when maximum (list "maximum" maximum))
                 (when default (list "default" default)))))

(defun tool-annotations (read-only idempotent)
  (jobject "readOnlyHint" (if read-only :true :false)
           "destructiveHint" :false
           "idempotentHint" (if idempotent :true :false)
           "openWorldHint" :false))

(defparameter *mcp-tools*
  (jarray
   (jobject
    "name" "search_memory_sheets"
    "title" "Rechercher des fiches de mémoire"
    "description"
    "Retrouve les fiches pertinentes par texte, alias et tags. Utiliser cet outil avant de conclure qu'une fiche n'existe pas. Une requête vide renvoie les fiches les plus importantes et les plus proches de leur échéance."
    "inputSchema"
    (object-schema
     (jobject
      "query" (string-schema :description "Mots, nom, thème ou expression à retrouver." :maximum-length 500)
      "tags" (array-schema (string-schema :maximum-length 64))
      "limit" (integer-schema :minimum 1 :maximum 50 :default 10))
     "query")
    "outputSchema"
    (object-schema
     (jobject "sheets" (array-schema (jobject "type" "object"))
              "count" (integer-schema :minimum 0))
     "sheets" "count")
    "annotations" (tool-annotations t t))
   (jobject
    "name" "list_due_memory_sheets"
    "title" "Lister les fiches à réviser"
    "description"
    "Liste les fiches dont l'échéance explicite est atteinte, éventuellement filtrées par tags. Ne calcule pas un intervalle de répétition implicite."
    "inputSchema"
    (object-schema
     (jobject
      "before" (string-schema :description "Date ISO 8601 limite. Par défaut : maintenant." :maximum-length 64)
      "tags" (array-schema (string-schema :maximum-length 64))
      "limit" (integer-schema :minimum 1 :maximum 50 :default 10)))
    "outputSchema"
    (object-schema
     (jobject "sheets" (array-schema (jobject "type" "object"))
              "count" (integer-schema :minimum 0))
     "sheets" "count")
    "annotations" (tool-annotations t t))
   (jobject
    "name" "get_memory_sheet"
    "title" "Lire une fiche de mémoire"
    "description"
    "Charge une fiche complète et ses observations récentes avant une révision ou une modification."
    "inputSchema"
    (object-schema
     (jobject
      "sheetId" (integer-schema :minimum 1)
      "observationLimit" (integer-schema :minimum 0 :maximum 100 :default 20))
     "sheetId")
    "outputSchema"
    (object-schema
     (jobject "found" (jobject "type" "boolean")
              "sheet" (jobject "type" (jarray "object" "null"))
              "observations" (array-schema (jobject "type" "object") :maximum 100))
     "found" "sheet" "observations")
    "annotations" (tool-annotations t t))
   (jobject
    "name" "save_memory_sheet"
    "title" "Enregistrer une fiche de mémoire"
    "description"
    "Crée une fiche ou remplace son contenu lorsque sheetId est fourni. N'enregistrer que ce que l'utilisateur demande explicitement de retenir. dueAt est une décision explicite ; son absence rend une nouvelle fiche immédiatement révisable et conserve l'échéance lors d'une mise à jour."
    "inputSchema"
    (object-schema
     (jobject
      "sheetId" (integer-schema :minimum 1)
      "title" (string-schema :maximum-length 200)
      "body" (string-schema :description "Contenu en texte ou Markdown." :maximum-length 50000)
      "summary" (string-schema :maximum-length 2000)
      "tags" (array-schema (string-schema :maximum-length 64))
      "aliases" (array-schema (string-schema :maximum-length 120))
      "importance" (integer-schema :minimum 1 :maximum 5 :default 3)
      "dueAt" (string-schema :description "Date ISO 8601, ou null pour ne pas planifier." :maximum-length 64 :nullable t))
     "title" "body")
    "outputSchema"
    (object-schema
     (jobject "saved" (jobject "type" "boolean")
              "created" (jobject "type" "boolean")
              "sheet" (jobject "type" (jarray "object" "null")))
     "saved" "created" "sheet")
    "annotations" (tool-annotations nil nil))
   (jobject
    "name" "record_review"
    "title" "Noter une observation de révision"
    "description"
    "Ajoute une observation factuelle après un échange et, seulement si nextReviewAt est fourni, modifie l'échéance. Un échec isolé doit être décrit avec son contexte plutôt que transformé en jugement global de maîtrise."
    "inputSchema"
    (object-schema
     (jobject
      "sheetId" (integer-schema :minimum 1)
      "outcome" (string-schema :enum '("recalled" "partial" "forgotten" "not_assessed"))
      "note" (string-schema :description "Observation concrète et parcimonieuse." :maximum-length 4000)
      "context" (jobject "type" "object" "additionalProperties" :true)
      "reviewedAt" (string-schema :description "Date ISO 8601. Par défaut : maintenant." :maximum-length 64)
      "nextReviewAt" (string-schema :description "Nouvelle échéance ISO 8601 ; null supprime l'échéance ; absence la conserve." :maximum-length 64 :nullable t))
     "sheetId" "outcome" "note")
    "outputSchema"
    (object-schema
     (jobject "recorded" (jobject "type" "boolean")
              "sheet" (jobject "type" (jarray "object" "null"))
              "observation" (jobject "type" (jarray "object" "null")))
     "recorded" "sheet" "observation")
    "annotations" (tool-annotations nil nil))))

(defun ensure-object (value description)
  (unless (json-object-p value)
    (invalid-parameters "~A must be an object." description))
  value)

(defun validate-object-keys (object allowed)
  (dolist (entry (json-object-entries object))
    (unless (member (car entry) allowed :test #'string=)
      (invalid-parameters "Unexpected argument ~S." (car entry)))))

(defun required-value (object key)
  (multiple-value-bind (value present) (json-object-get object key)
    (unless present
      (invalid-parameters "Missing required argument ~S." key))
    value))

(defun validated-string (value name maximum &key (allow-empty t))
  (unless (stringp value)
    (invalid-parameters "~A must be a string." name))
  (when (> (length value) maximum)
    (invalid-parameters "~A is too long." name))
  (when (and (not allow-empty) (string= (string-trim '(#\Space #\Tab #\Return #\Linefeed) value) ""))
    (invalid-parameters "~A must not be empty." name))
  (when (find (code-char 0) value)
    (invalid-parameters "~A contains a null character." name))
  value)

(defun optional-string (object key default maximum)
  (multiple-value-bind (value present) (json-object-get object key)
    (if present
        (validated-string value key maximum)
        default)))

(defun validated-integer (value name minimum maximum)
  (unless (and (integerp value) (<= minimum value maximum))
    (invalid-parameters "~A must be an integer between ~D and ~D."
                        name minimum maximum))
  value)

(defun optional-integer (object key default minimum maximum)
  (multiple-value-bind (value present) (json-object-get object key)
    (if present
        (validated-integer value key minimum maximum)
        default)))

(defun normalized-string-array (object key maximum-count maximum-length &key downcase)
  (multiple-value-bind (value present) (json-object-get object key)
    (unless present
      (return-from normalized-string-array (jarray)))
    (unless (json-array-p value)
      (invalid-parameters "~A must be an array of strings." key))
    (when (> (length (json-array-items value)) maximum-count)
      (invalid-parameters "~A contains too many values." key))
    (let ((items '()))
      (dolist (item (json-array-items value))
        (let* ((text (validated-string item key maximum-length :allow-empty nil))
               (trimmed (string-trim '(#\Space #\Tab #\Return #\Linefeed) text))
               (normalized (if downcase (string-downcase trimmed) trimmed)))
          (unless (member normalized items :test #'string-equal)
            (push normalized items))))
      (%make-json-array (nreverse items)))))

(defun boolean-json (value)
  (if value "true" "false"))

(defun timestamp-arguments (object key prefix)
  (multiple-value-bind (value present) (json-object-get object key)
    (cond
      ((not present)
       (list (cons (format nil "~A_present" prefix) "false")
             (cons (format nil "~A_is_null" prefix) "false")
             (cons (format nil "~A" prefix) "1970-01-01T00:00:00Z")))
      ((eq value :null)
       (list (cons (format nil "~A_present" prefix) "true")
             (cons (format nil "~A_is_null" prefix) "true")
             (cons (format nil "~A" prefix) "1970-01-01T00:00:00Z")))
      (t
       (list (cons (format nil "~A_present" prefix) "true")
             (cons (format nil "~A_is_null" prefix) "false")
             (cons (format nil "~A" prefix)
                   (validated-string value key 64 :allow-empty nil)))))))

(defun plain-timestamp-arguments (object key prefix)
  (multiple-value-bind (value present) (json-object-get object key)
    (list (cons (format nil "~A_present" prefix) (boolean-json present))
          (cons prefix
                (if present
                    (validated-string value key 64 :allow-empty nil)
                    "1970-01-01T00:00:00Z")))))

(defun database-result-success-p (result key)
  (multiple-value-bind (value present) (json-object-get result key)
    (and present (eq value :true))))

(defun call-search-memory-sheets (arguments)
  (validate-object-keys arguments '("query" "tags" "limit"))
  (let ((query (validated-string (required-value arguments "query") "query" 500))
        (tags (normalized-string-array arguments "tags" 50 64 :downcase t))
        (limit (optional-integer arguments "limit" 10 1 50)))
    (database-query-json
     "search_memory_sheets" +sql-search-memory-sheets+
     (list (cons "query" query)
           (cons "tags" (json-encode tags))
           (cons "limit" (princ-to-string limit))))))

(defun call-list-due-memory-sheets (arguments)
  (validate-object-keys arguments '("before" "tags" "limit"))
  (let ((before (optional-string arguments "before" "now" 64))
        (tags (normalized-string-array arguments "tags" 50 64 :downcase t))
        (limit (optional-integer arguments "limit" 10 1 50)))
    (database-query-json
     "list_due_memory_sheets" +sql-list-due-memory-sheets+
     (list (cons "before" before)
           (cons "tags" (json-encode tags))
           (cons "limit" (princ-to-string limit))))))

(defun call-get-memory-sheet (arguments)
  (validate-object-keys arguments '("sheetId" "observationLimit"))
  (let ((sheet-id (validated-integer (required-value arguments "sheetId")
                                     "sheetId" 1 most-positive-fixnum))
        (limit (optional-integer arguments "observationLimit" 20 0 100)))
    (database-query-json
     "get_memory_sheet" +sql-get-memory-sheet+
     (list (cons "sheet_id" (princ-to-string sheet-id))
           (cons "observation_limit" (princ-to-string limit))))))

(defun call-save-memory-sheet (arguments)
  (validate-object-keys
   arguments '("sheetId" "title" "body" "summary" "tags" "aliases"
               "importance" "dueAt"))
  (multiple-value-bind (sheet-id sheet-id-present)
      (json-object-get arguments "sheetId")
    (when sheet-id-present
      (validated-integer sheet-id "sheetId" 1 most-positive-fixnum))
    (let* ((title (validated-string (required-value arguments "title")
                                    "title" 200 :allow-empty nil))
           (body (validated-string (required-value arguments "body")
                                   "body" 50000 :allow-empty nil))
           (summary (optional-string arguments "summary" "" 2000))
           (tags (normalized-string-array arguments "tags" 50 64 :downcase t))
           (aliases (normalized-string-array arguments "aliases" 50 120))
           (importance (optional-integer arguments "importance" 3 1 5))
           (variables
             (append
              (list (cons "title" title)
                    (cons "body" body)
                    (cons "summary" summary)
                    (cons "tags" (json-encode tags))
                    (cons "aliases" (json-encode aliases))
                    (cons "importance" (princ-to-string importance)))
              (timestamp-arguments arguments "dueAt" "due")))
           (result
             (if sheet-id-present
                 (database-query-json
                  "save_memory_sheet_update" +sql-update-memory-sheet+
                  (cons (cons "sheet_id" (princ-to-string sheet-id)) variables))
                 (database-query-json
                  "save_memory_sheet_create" +sql-create-memory-sheet+ variables))))
      (values result (database-result-success-p result "saved")))))

(defun call-record-review (arguments)
  (validate-object-keys
   arguments '("sheetId" "outcome" "note" "context" "reviewedAt" "nextReviewAt"))
  (let* ((sheet-id (validated-integer (required-value arguments "sheetId")
                                      "sheetId" 1 most-positive-fixnum))
         (outcome (validated-string (required-value arguments "outcome")
                                    "outcome" 32 :allow-empty nil))
         (note (validated-string (required-value arguments "note")
                                 "note" 4000 :allow-empty nil))
         (context (multiple-value-bind (value present)
                      (json-object-get arguments "context")
                    (if present (ensure-object value "context") (jobject)))))
    (unless (member outcome '("recalled" "partial" "forgotten" "not_assessed")
                    :test #'string=)
      (invalid-parameters "outcome is not supported."))
    (let* ((variables
             (append
              (list (cons "sheet_id" (princ-to-string sheet-id))
                    (cons "outcome" outcome)
                    (cons "note" note)
                    (cons "context" (json-encode context)))
              (plain-timestamp-arguments arguments "reviewedAt" "reviewed_at")
              (timestamp-arguments arguments "nextReviewAt" "next_review")))
           (result (database-query-json
                    "record_review" +sql-record-review+ variables)))
      (values result (database-result-success-p result "recorded")))))

(defun mcp-tool-result (structured &key (success t) message)
  (jobject
   "content" (jarray
               (jobject "type" "text"
                        "text" (or message (json-encode structured))))
   "structuredContent" structured
   "isError" (if success :false :true)))

(defun invoke-mcp-tool (name arguments)
  (handler-case
      (cond
        ((string= name "search_memory_sheets")
         (mcp-tool-result (call-search-memory-sheets arguments)))
        ((string= name "list_due_memory_sheets")
         (mcp-tool-result (call-list-due-memory-sheets arguments)))
        ((string= name "get_memory_sheet")
         (mcp-tool-result (call-get-memory-sheet arguments)))
        ((string= name "save_memory_sheet")
         (multiple-value-bind (result success)
             (call-save-memory-sheet arguments)
           (mcp-tool-result result :success success
                                  :message (unless success "Fiche introuvable."))))
        ((string= name "record_review")
         (multiple-value-bind (result success)
             (call-record-review arguments)
           (mcp-tool-result result :success success
                                  :message (unless success "Fiche introuvable."))))
        (t (invalid-parameters "Unknown tool ~S." name)))
    (database-error (condition)
      (format *error-output* "Database operation ~A failed: ~A~%"
              name (database-error-detail condition))
      (finish-output *error-output*)
      (mcp-tool-result
       (jobject "error" "database_unavailable")
       :success nil
       :message "La base de données Vision est temporairement indisponible."))))

(defun mcp-success-response (id result)
  (jobject "jsonrpc" "2.0" "id" id "result" result))

(defun mcp-error-response (id code message &optional data)
  (jobject "jsonrpc" "2.0"
           "id" id
           "error" (apply #'jobject
                          (append (list "code" code "message" message)
                                  (when data (list "data" data))))))

(defun protocol-version-p (value)
  (and (stringp value)
       (= (length value) 10)
       (char= (char value 4) #\-)
       (char= (char value 7) #\-)
       (loop for index from 0 below 10
             always (or (member index '(4 7))
                        (digit-char-p (char value index))))))

(defun initialize-result (params)
  (let ((requested
          (multiple-value-bind (value present)
              (json-object-get params "protocolVersion")
            (if (and present (protocol-version-p value))
                value
                +mcp-default-protocol-version+))))
    (jobject
     "protocolVersion" requested
     "capabilities" (jobject "tools" (jobject "listChanged" :false))
     "serverInfo" (jobject "name" "vision" "title" "Vision" "version" *version*)
     "instructions"
     "Vision conserve les informations que Jean-Christophe demande explicitement de mémoriser. Rechercher puis lire les fiches pertinentes avant une révision. Noter les réussites, oublis et indices de compréhension avec parcimonie et leur contexte ; ne jamais déduire une maîtrise globale d'un seul échange. La prochaine échéance est une décision explicite, pas un intervalle automatique.")))

(defun dispatch-mcp-request (request)
  (ensure-object request "JSON-RPC request")
  (multiple-value-bind (jsonrpc jsonrpc-present) (json-object-get request "jsonrpc")
    (unless (and jsonrpc-present (stringp jsonrpc) (string= jsonrpc "2.0"))
      (return-from dispatch-mcp-request
        (values 200 (mcp-error-response :null -32600 "Invalid Request")))))
  (multiple-value-bind (id id-present) (json-object-get request "id")
    (multiple-value-bind (method method-present) (json-object-get request "method")
      (unless (and method-present (stringp method))
        (return-from dispatch-mcp-request
          (values 200 (mcp-error-response (if id-present id :null)
                                          -32600 "Invalid Request"))))
      (multiple-value-bind (raw-params params-present) (json-object-get request "params")
        (let ((params (if params-present
                          (ensure-object raw-params "params")
                          (jobject))))
          (unless id-present
            ;; Les notifications ne peuvent pas déclencher silencieusement un outil d'écriture.
            (return-from dispatch-mcp-request (values 202 nil)))
          (handler-case
              (cond
                ((string= method "initialize")
                 (values 200 (mcp-success-response id (initialize-result params))))
                ((string= method "ping")
                 (values 200 (mcp-success-response id (jobject))))
                ((string= method "tools/list")
                 (validate-object-keys params '("cursor"))
                 (values 200
                         (mcp-success-response id (jobject "tools" *mcp-tools*))))
                ((string= method "tools/call")
                 (validate-object-keys params '("name" "arguments"))
                 (let ((name (validated-string (required-value params "name")
                                               "name" 128 :allow-empty nil))
                       (arguments
                         (multiple-value-bind (value present)
                             (json-object-get params "arguments")
                           (if present
                               (ensure-object value "arguments")
                               (jobject)))))
                   (values 200
                           (mcp-success-response
                            id (invoke-mcp-tool name arguments)))))
                (t
                 (values 200 (mcp-error-response id -32601 "Method not found"))))
            (invalid-parameters (condition)
              (values 200
                      (mcp-error-response
                       id -32602 "Invalid params"
                       (jobject "message" (invalid-parameters-message condition)))))))))))

(defun handle-mcp-message (body)
  (handler-case
      (multiple-value-bind (status response)
          (dispatch-mcp-request (parse-json body))
        (values status
                (if (= status 202) "Accepted" "OK")
                (and response (json-encode response))))
    (json-error (condition)
      (values 200 "OK"
              (json-encode
               (mcp-error-response
                :null -32700 "Parse error"
                (jobject "message" (json-error-message condition))))))
    (invalid-parameters (condition)
      (values 200 "OK"
              (json-encode
               (mcp-error-response
                :null -32600 "Invalid Request"
                (jobject "message" (invalid-parameters-message condition))))))))
