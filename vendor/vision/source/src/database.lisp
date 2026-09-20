(in-package #:vision)

(define-condition database-error (error)
  ((message :initarg :message :reader database-error-message)
   (detail :initarg :detail :reader database-error-detail)))

(defun database-fail (message detail)
  (error 'database-error :message message :detail detail))

(defun slurp-character-stream (stream)
  (with-output-to-string (output)
    (loop for character = (read-char stream nil nil)
          while character
          do (write-char character output))))

(defun run-database-process (command sql)
  ;; UIOP:RUN-PROGRAM ne peut traiter qu'un flux actif à la fois. Avec une
  ;; entrée Lisp et deux sorties capturées, il crée donc des fichiers
  ;; temporaires. Un exécutable sauvegardé pendant un build Nix conserverait
  ;; alors /build comme répertoire temporaire. LAUNCH-PROGRAM et ses tubes
  ;; évitent tout chemin de construction incorporé dans l'image SBCL.
  (handler-case
      (let* ((process (uiop:launch-program
                       command
                       :input :stream
                       :output :stream
                       :error-output :output
                       :external-format :utf-8))
             (input (uiop:process-info-input process))
             (output (uiop:process-info-output process)))
        (unwind-protect
             (progn
               (write-string sql input)
               (finish-output input)
               (close input)
               (setf input nil)
               (values (slurp-character-stream output)
                       (uiop:wait-process process)))
          (when input
            (ignore-errors (close input)))
          (ignore-errors (uiop:close-streams process))))
    (error (condition)
      (database-fail "PostgreSQL process could not be executed."
                     (princ-to-string condition)))))

(defun database-query-json (operation sql variables)
  (let ((command
          (append
           (list (or (sb-ext:posix-getenv "VISION_PSQL") "psql")
                 "--no-psqlrc" "--quiet" "--tuples-only" "--no-align"
                 "--set=ON_ERROR_STOP=1" "--set=VERBOSITY=terse"
                 "--set" (format nil "operation=~A" operation))
           (loop for (name . value) in variables
                 collect "--set"
                 collect (format nil "~A=~A" name value))
           (list "--file=-"))))
    ;; psql n'applique la citation :'variable' que lorsqu'il lit son entrée,
    ;; pas quand la requête entière est fournie avec --command.
    (multiple-value-bind (output exit-code)
        (run-database-process command sql)
      (unless (zerop exit-code)
        (database-fail
         "PostgreSQL request failed."
         (string-trim '(#\Space #\Tab #\Return #\Linefeed) output)))
      (let ((payload (string-trim '(#\Space #\Tab #\Return #\Linefeed)
                                  output)))
        (when (string= payload "")
          (database-fail "PostgreSQL returned no result." "empty output"))
        (handler-case
            (parse-json payload)
          (json-error (condition)
            (database-fail "PostgreSQL returned invalid JSON."
                           (json-error-message condition))))))))

(defparameter +sql-search-memory-sheets+
  "WITH input AS (
     SELECT :'query'::text AS query,
            websearch_to_tsquery('simple', :'query'::text) AS terms,
            :'tags'::jsonb AS tags
   ), selected AS (
     SELECT s.id, s.title, s.summary, s.tags, s.aliases, s.importance,
            s.due_at AS \"dueAt\", s.last_reviewed_at AS \"lastReviewedAt\",
            s.last_outcome AS \"lastOutcome\", s.review_count AS \"reviewCount\",
            s.updated_at AS \"updatedAt\",
            CASE WHEN input.query = '' THEN 0::real ELSE
              ts_rank(
                to_tsvector('simple', s.title || ' ' || s.summary || ' ' || s.body),
                input.terms)
            END AS rank
       FROM vision_memory_sheets AS s
       CROSS JOIN input
      WHERE s.archived_at IS NULL
        AND (
          input.query = ''
          OR to_tsvector(
               'simple', s.title || ' ' || s.summary || ' ' || s.body
             ) @@ input.terms
          OR to_tsvector(
               'simple', array_to_string(s.tags, ' ') || ' '
                 || array_to_string(s.aliases, ' ')
             ) @@ input.terms
          OR strpos(lower(
               s.title || ' ' || s.summary || ' ' || s.body || ' '
                 || array_to_string(s.tags, ' ') || ' '
                 || array_to_string(s.aliases, ' ')
             ), lower(input.query)) > 0
        )
        AND NOT EXISTS (
          SELECT 1
            FROM jsonb_array_elements_text(input.tags) AS requested(tag)
           WHERE NOT EXISTS (
             SELECT 1 FROM unnest(s.tags) AS stored(tag)
              WHERE lower(stored.tag) = lower(requested.tag)
           )
        )
      ORDER BY rank DESC, s.importance DESC,
               s.due_at ASC NULLS LAST, s.updated_at DESC
      LIMIT :'limit'::integer
   )
   SELECT jsonb_build_object(
     'sheets', COALESCE(
       jsonb_agg(to_jsonb(selected) - 'rank'
                 ORDER BY rank DESC, importance DESC, \"dueAt\" ASC NULLS LAST,
                          \"updatedAt\" DESC),
       '[]'::jsonb),
     'count', count(*)
   )
   FROM selected")

(defparameter +sql-list-due-memory-sheets+
  "WITH input AS (
     SELECT :'before'::timestamptz AS before, :'tags'::jsonb AS tags
   ), selected AS (
     SELECT s.id, s.title, s.summary, s.tags, s.aliases, s.importance,
            s.due_at AS \"dueAt\", s.last_reviewed_at AS \"lastReviewedAt\",
            s.last_outcome AS \"lastOutcome\", s.review_count AS \"reviewCount\",
            s.updated_at AS \"updatedAt\"
       FROM vision_memory_sheets AS s
       CROSS JOIN input
      WHERE s.archived_at IS NULL
        AND s.due_at IS NOT NULL
        AND s.due_at <= input.before
        AND NOT EXISTS (
          SELECT 1
            FROM jsonb_array_elements_text(input.tags) AS requested(tag)
           WHERE NOT EXISTS (
             SELECT 1 FROM unnest(s.tags) AS stored(tag)
              WHERE lower(stored.tag) = lower(requested.tag)
           )
        )
      ORDER BY s.due_at ASC, s.importance DESC, s.updated_at DESC
      LIMIT :'limit'::integer
   )
   SELECT jsonb_build_object(
     'sheets', COALESCE(
       jsonb_agg(to_jsonb(selected)
                 ORDER BY \"dueAt\" ASC, importance DESC, \"updatedAt\" DESC),
       '[]'::jsonb),
     'count', count(*)
   )
   FROM selected")

(defparameter +sql-get-memory-sheet+
  "WITH selected AS (
     SELECT s.id, s.title, s.body, s.summary, s.tags, s.aliases, s.importance,
            s.due_at AS \"dueAt\", s.last_reviewed_at AS \"lastReviewedAt\",
            s.last_outcome AS \"lastOutcome\", s.review_count AS \"reviewCount\",
            s.created_at AS \"createdAt\", s.updated_at AS \"updatedAt\"
       FROM vision_memory_sheets AS s
      WHERE s.id = :'sheet_id'::bigint AND s.archived_at IS NULL
   ), observations AS (
     SELECT o.id, o.outcome, o.note, o.context,
            o.reviewed_at AS \"reviewedAt\",
            o.next_review_at AS \"nextReviewAt\"
       FROM vision_memory_observations AS o
      WHERE o.sheet_id = :'sheet_id'::bigint
      ORDER BY o.reviewed_at DESC, o.id DESC
      LIMIT :'observation_limit'::integer
   )
   SELECT COALESCE(
     (SELECT jsonb_build_object(
        'found', true,
        'sheet', to_jsonb(selected),
        'observations', COALESCE(
          (SELECT jsonb_agg(to_jsonb(observations)
                            ORDER BY \"reviewedAt\" DESC, id DESC)
             FROM observations),
          '[]'::jsonb)
      ) FROM selected),
     jsonb_build_object('found', false, 'sheet', null, 'observations', '[]'::jsonb)
   )")

(defparameter +sql-create-memory-sheet+
  "WITH inserted AS (
     INSERT INTO vision_memory_sheets
       (title, body, summary, tags, aliases, importance, due_at)
     VALUES (
       :'title'::text,
       :'body'::text,
       :'summary'::text,
       ARRAY(SELECT jsonb_array_elements_text(:'tags'::jsonb)),
       ARRAY(SELECT jsonb_array_elements_text(:'aliases'::jsonb)),
       :'importance'::smallint,
       CASE
         WHEN :'due_present'::boolean = false THEN now()
         WHEN :'due_is_null'::boolean = true THEN NULL
         ELSE :'due'::timestamptz
       END
     )
     RETURNING id, title, body, summary, tags, aliases, importance,
               due_at AS \"dueAt\", last_reviewed_at AS \"lastReviewedAt\",
               last_outcome AS \"lastOutcome\", review_count AS \"reviewCount\",
               created_at AS \"createdAt\", updated_at AS \"updatedAt\"
   )
   SELECT jsonb_build_object(
     'saved', true, 'created', true, 'sheet', to_jsonb(inserted)
   ) FROM inserted")

(defparameter +sql-update-memory-sheet+
  "WITH updated AS (
     UPDATE vision_memory_sheets
        SET title = :'title'::text,
            body = :'body'::text,
            summary = :'summary'::text,
            tags = ARRAY(SELECT jsonb_array_elements_text(:'tags'::jsonb)),
            aliases = ARRAY(SELECT jsonb_array_elements_text(:'aliases'::jsonb)),
            importance = :'importance'::smallint,
            due_at = CASE
              WHEN :'due_present'::boolean = false THEN due_at
              WHEN :'due_is_null'::boolean = true THEN NULL
              ELSE :'due'::timestamptz
            END,
            updated_at = now()
      WHERE id = :'sheet_id'::bigint AND archived_at IS NULL
      RETURNING id, title, body, summary, tags, aliases, importance,
                due_at AS \"dueAt\", last_reviewed_at AS \"lastReviewedAt\",
                last_outcome AS \"lastOutcome\", review_count AS \"reviewCount\",
                created_at AS \"createdAt\", updated_at AS \"updatedAt\"
   )
   SELECT COALESCE(
     (SELECT jsonb_build_object(
        'saved', true, 'created', false, 'sheet', to_jsonb(updated)
      ) FROM updated),
     jsonb_build_object('saved', false, 'created', false, 'sheet', null,
                        'error', 'not_found')
   )")

(defparameter +sql-record-review+
  "WITH target AS (
     SELECT id FROM vision_memory_sheets
      WHERE id = :'sheet_id'::bigint AND archived_at IS NULL
   ), inserted AS (
     INSERT INTO vision_memory_observations
       (sheet_id, outcome, note, context, reviewed_at, next_review_at)
     SELECT id, :'outcome'::text, :'note'::text, :'context'::jsonb,
            CASE WHEN :'reviewed_at_present'::boolean
                 THEN :'reviewed_at'::timestamptz ELSE now() END,
            CASE
              WHEN :'next_review_present'::boolean = false THEN NULL
              WHEN :'next_review_is_null'::boolean = true THEN NULL
              ELSE :'next_review'::timestamptz
            END
       FROM target
     RETURNING id, sheet_id, outcome, note, context, reviewed_at, next_review_at
   ), updated AS (
     UPDATE vision_memory_sheets AS s
        SET last_reviewed_at = i.reviewed_at,
            last_outcome = i.outcome,
            review_count = s.review_count + 1,
            due_at = CASE
              WHEN :'next_review_present'::boolean = false THEN s.due_at
              WHEN :'next_review_is_null'::boolean = true THEN NULL
              ELSE :'next_review'::timestamptz
            END,
            updated_at = now()
       FROM inserted AS i
      WHERE s.id = i.sheet_id
      RETURNING s.id, s.due_at AS \"dueAt\", s.last_reviewed_at AS \"lastReviewedAt\",
                s.last_outcome AS \"lastOutcome\", s.review_count AS \"reviewCount\"
   )
   SELECT COALESCE(
     (SELECT jsonb_build_object(
        'recorded', true,
        'sheet', to_jsonb(updated),
        'observation', jsonb_build_object(
          'id', inserted.id,
          'sheetId', inserted.sheet_id,
          'outcome', inserted.outcome,
          'note', inserted.note,
          'context', inserted.context,
          'reviewedAt', inserted.reviewed_at,
          'nextReviewAt', inserted.next_review_at
        )
      ) FROM inserted CROSS JOIN updated),
     jsonb_build_object('recorded', false, 'sheet', null, 'observation', null,
                        'error', 'not_found')
   )")
