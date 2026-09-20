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
    "Liste les fiches dont l'échéance est atteinte, qu'elle ait été calculée par FSRS ou fixée manuellement, éventuellement filtrées par tags."
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
    "Ajoute une observation factuelle après un échange. Fournir rating seulement si le rappel a réellement été évalué : 1=Again (échec), 2=Hard (rappel réussi avec difficulté), 3=Good (rappel correct), 4=Easy (rappel immédiat et assuré). FSRS calcule alors l'échéance. En cas de fatigue, ambiguïté, aide excessive ou évaluation insuffisante, omettre rating : l'observation reste qualitative et ne modifie pas l'état FSRS. nextReviewAt est une dérogation manuelle, utilisable seulement sans rating."
    "inputSchema"
    (object-schema
     (jobject
      "sheetId" (integer-schema :minimum 1)
      "outcome" (string-schema :enum '("recalled" "partial" "forgotten" "not_assessed"))
      "note" (string-schema :description "Observation concrète et parcimonieuse." :maximum-length 4000)
      "context" (jobject "type" "object" "additionalProperties" :true)
      "reviewedAt" (string-schema :description "Date ISO 8601. Par défaut : maintenant." :maximum-length 64)
      "rating" (integer-schema :description "Note FSRS : 1=Again, 2=Hard, 3=Good, 4=Easy. Omettre si le rappel n'a pas été évalué de façon fiable." :minimum 1 :maximum 4)
      "nextReviewAt" (string-schema :description "Dérogation manuelle sans rating : date ISO 8601 ; null supprime l'échéance ; absence la conserve." :maximum-length 64 :nullable t))
     "sheetId" "outcome" "note")
    "outputSchema"
    (object-schema
     (jobject "recorded" (jobject "type" "boolean")
              "sheet" (jobject "type" (jarray "object" "null"))
              "observation" (jobject "type" (jarray "object" "null"))
              "scheduling" (jobject "type" "object" "additionalProperties" :true))
     "recorded" "sheet" "observation" "scheduling")
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

(defun database-object-value (object key)
  (multiple-value-bind (value present) (json-object-get object key)
    (unless present
      (database-fail "Malformed PostgreSQL result."
                     (format nil "Missing field ~S." key)))
    value))

(defun database-result-error (result)
  (multiple-value-bind (value present) (json-object-get result "error")
    (and present value)))

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

(defun call-qualitative-review
    (arguments sheet-id outcome note context)
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
    (values result (database-result-success-p result "recorded"))))

(defun fsrs-state-from-database (sheet)
  (let ((stability (database-object-value sheet "stability"))
        (difficulty (database-object-value sheet "difficulty")))
    (cond
      ((and (eq stability :null) (eq difficulty :null)) nil)
      ((and (fsrs-finite-number-p stability)
            (fsrs-finite-number-p difficulty))
       (make-fsrs-memory-state (coerce stability 'double-float)
                               (coerce difficulty 'double-float)))
      (t
       (database-fail "Invalid FSRS state."
                      "Stability and difficulty must both be null or finite.")))))

(defun call-fsrs-review
    (arguments sheet-id outcome note context rating &optional (attempt 1))
  (let* ((prepared
           (database-query-json
            "prepare_fsrs_review" +sql-prepare-fsrs-review+
            (append
             (list (cons "sheet_id" (princ-to-string sheet-id)))
             (plain-timestamp-arguments arguments "reviewedAt" "reviewed_at"))))
         (found (database-object-value prepared "found")))
    (unless (eq found :true)
      (return-from call-fsrs-review
        (values
         (jobject "recorded" :false "sheet" :null "observation" :null
                  "scheduling" (jobject "applied" :false)
                  "error" "not_found")
         nil)))
    (let* ((sheet (database-object-value prepared "sheet"))
           (settings (database-object-value prepared "settings"))
           (model-version (database-object-value settings "modelVersion"))
           (implementation-version
             (database-object-value settings "implementationVersion"))
           (desired-retention
             (database-object-value settings "desiredRetention"))
           (parameters
             (fsrs-json-parameters
              (database-object-value settings "parameters")))
           (elapsed-days (database-object-value sheet "elapsedDays"))
           (reviewed-at (database-object-value sheet "reviewedAt"))
           (previous-state (fsrs-state-from-database sheet)))
      (unless (and (stringp model-version)
                   (string= model-version +fsrs-model-version+))
        (database-fail "Unsupported FSRS model."
                       (format nil "Expected ~A, received ~A."
                               +fsrs-model-version+ model-version)))
      (unless (eq (database-object-value sheet "chronological") :true)
        (invalid-parameters
         "reviewedAt precedes the last FSRS review; an incremental FSRS update must be chronological."))
      (unless (and (integerp elapsed-days) (>= elapsed-days 0))
        (database-fail "Invalid FSRS state." "elapsedDays must be non-negative."))
      (unless (and (fsrs-finite-number-p desired-retention)
                   (< 0.0d0 (coerce desired-retention 'double-float) 1.0d0))
        (database-fail "Invalid FSRS settings."
                       "desiredRetention must be between zero and one."))
      (multiple-value-bind (next-state interval scheduled-days)
          (fsrs-schedule previous-state rating elapsed-days
                         desired-retention parameters)
        (let* ((variables
                 (list
                  (cons "sheet_id" (princ-to-string sheet-id))
                  (cons "expected_review_count"
                        (princ-to-string
                         (database-object-value sheet "reviewCount")))
                  (cons "expected_fsrs_review_count"
                        (princ-to-string
                         (database-object-value sheet "fsrsReviewCount")))
                  (cons "outcome" outcome)
                  (cons "note" note)
                  (cons "context" (json-encode context))
                  (cons "reviewed_at" reviewed-at)
                  (cons "rating" (princ-to-string rating))
                  (cons "scheduler_version"
                        (format nil "~A/~A" model-version implementation-version))
                  (cons "model_version" model-version)
                  (cons "implementation_version" implementation-version)
                  (cons "desired_retention" (json-encode
                                              (coerce desired-retention
                                                      'double-float)))
                  (cons "elapsed_days" (princ-to-string elapsed-days))
                  (cons "new_stability"
                        (json-encode
                         (fsrs-memory-state-stability next-state)))
                  (cons "new_difficulty"
                        (json-encode
                         (fsrs-memory-state-difficulty next-state)))
                  (cons "interval_days" (json-encode interval))
                  (cons "scheduled_days" (princ-to-string scheduled-days))))
               (result
                 (database-query-json
                  "record_fsrs_review" +sql-record-fsrs-review+ variables)))
          (cond
            ((database-result-success-p result "recorded")
             (values result t))
            ((and (string= (or (database-result-error result) "") "conflict")
                  (< attempt 3))
             (call-fsrs-review arguments sheet-id outcome note context rating
                               (1+ attempt)))
            ((string= (or (database-result-error result) "") "conflict")
             (database-fail "Concurrent review update failed."
                            "The memory sheet changed during three FSRS retries."))
            (t (values result nil))))))))

(defun call-record-review (arguments)
  (validate-object-keys
   arguments '("sheetId" "outcome" "note" "context" "reviewedAt" "rating"
               "nextReviewAt"))
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
    (multiple-value-bind (rating rating-present)
        (json-object-get arguments "rating")
      (multiple-value-bind (next-review-at next-review-at-present)
          (json-object-get arguments "nextReviewAt")
        (declare (ignore next-review-at))
        (when rating-present
          (validated-integer rating "rating" 1 4)
          (when next-review-at-present
            (invalid-parameters
             "rating and nextReviewAt are mutually exclusive; FSRS determines the due date."))
          (when (string= outcome "not_assessed")
            (invalid-parameters
             "rating must be omitted when outcome is not_assessed."))
          (when (and (= rating 1) (string= outcome "recalled"))
            (invalid-parameters "rating 1 (Again) is incompatible with recalled."))
          (when (and (> rating 1) (string= outcome "forgotten"))
            (invalid-parameters
             "ratings 2 to 4 indicate successful recall and are incompatible with forgotten.")))
        (if rating-present
            (call-fsrs-review arguments sheet-id outcome note context rating)
            (call-qualitative-review
             arguments sheet-id outcome note context))))))

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
     "Vision conserve les informations que Jean-Christophe demande explicitement de mémoriser. Rechercher puis lire les fiches pertinentes avant une révision. Noter les réussites, oublis et indices de compréhension avec parcimonie et leur contexte ; ne jamais déduire une maîtrise globale d'un seul échange. Après une véritable tentative de rappel, fournir une note FSRS : 1=échec, 2=rappel difficile mais réussi, 3=rappel correct, 4=rappel immédiat et assuré. En cas de fatigue, ambiguïté, aide excessive ou évaluation insuffisante, omettre la note : l'observation ne changera pas la planification.")))

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
