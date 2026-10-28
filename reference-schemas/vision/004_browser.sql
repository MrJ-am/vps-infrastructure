BEGIN;

-- Les observations originales restent immuables ; les corrections sont datées.
CREATE TABLE IF NOT EXISTS vision_observation_corrections (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  observation_id bigint NOT NULL REFERENCES vision_memory_observations(id),
  note text NOT NULL CHECK (char_length(note) BETWEEN 1 AND 4000),
  context jsonb NOT NULL CHECK (jsonb_typeof(context) = 'object'),
  author text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX IF NOT EXISTS vision_corrections_observation_idx
  ON vision_observation_corrections(observation_id, id DESC);
CREATE TABLE IF NOT EXISTS vision_sheet_edits (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  sheet_id bigint NOT NULL REFERENCES vision_memory_sheets(id),
  author text NOT NULL,
  before_value jsonb,
  after_value jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE OR REPLACE VIEW vision_browser_sheets AS
SELECT s.id, s.title, s.summary, s.tags, s.aliases, s.importance,
  s.due_at AS "dueAt", s.last_reviewed_at AS "lastReviewedAt",
  s.last_outcome AS "lastOutcome", s.review_count AS "reviewCount",
  s.fsrs_stability AS "fsrsStability", s.fsrs_difficulty AS "fsrsDifficulty",
  s.fsrs_last_reviewed_at AS "fsrsLastReviewedAt",
  s.fsrs_review_count AS "fsrsReviewCount", s.fsrs_model_version AS "fsrsModelVersion",
  s.created_at AS "createdAt", s.updated_at AS "updatedAt", s.archived_at AS "archivedAt",
  cfg.desired_retention AS "desiredRetention",
  CASE WHEN s.fsrs_stability IS NULL OR s.fsrs_last_reviewed_at IS NULL THEN NULL
    ELSE power(1.0 + GREATEST(0.0, round(extract(epoch FROM (now() - s.fsrs_last_reviewed_at))/86400.0))
      / s.fsrs_stability * (power(0.9, -1.0/cfg.parameters[21])-1.0), -cfg.parameters[21])
  END AS retrievability,
  CASE WHEN s.archived_at IS NOT NULL THEN 'archived'
    WHEN s.review_count = 0 THEN 'new'
    WHEN s.due_at IS NULL THEN 'unscheduled'
    WHEN s.due_at <= now() THEN 'due' ELSE 'scheduled' END AS state
FROM vision_memory_sheets s CROSS JOIN vision_scheduler_settings cfg;

CREATE OR REPLACE FUNCTION vision_web_list(p jsonb) RETURNS jsonb LANGUAGE plpgsql AS $$
DECLARE result jsonb;
BEGIN
  WITH filtered AS MATERIALIZED (
    SELECT v.* FROM vision_browser_sheets v JOIN vision_memory_sheets s USING(id)
    WHERE (CASE p->>'state'
      WHEN 'all' THEN true WHEN 'archived' THEN s.archived_at IS NOT NULL
      ELSE s.archived_at IS NULL END)
    AND (CASE p->>'state'
      WHEN 'due' THEN s.due_at <= now() WHEN 'new' THEN s.review_count = 0
      WHEN 'unscheduled' THEN s.due_at IS NULL
      WHEN 'scheduled' THEN s.due_at > now() ELSE true END)
    AND (p->>'query' = '' OR
      to_tsvector('simple', s.title || ' ' || s.summary || ' ' || s.body || ' ' ||
        array_to_string(s.tags,' ') || ' ' || array_to_string(s.aliases,' '))
        @@ websearch_to_tsquery('simple',p->>'query')
      OR strpos(lower(s.title || ' ' || s.summary || ' ' || s.body || ' ' ||
        array_to_string(s.tags,' ') || ' ' || array_to_string(s.aliases,' ')), lower(p->>'query')) > 0)
    AND (jsonb_array_length(p->'tags') = 0 OR CASE p->>'tagMode' WHEN 'any' THEN
      EXISTS (SELECT 1 FROM jsonb_array_elements_text(p->'tags') t(tag)
        JOIN unnest(s.tags) u(tag) ON lower(t.tag)=lower(u.tag)) ELSE
      NOT EXISTS (SELECT 1 FROM jsonb_array_elements_text(p->'tags') t(tag)
        WHERE NOT EXISTS (SELECT 1 FROM unnest(s.tags) u(tag) WHERE lower(t.tag)=lower(u.tag))) END)
    AND (NOT (p ? 'importance') OR s.importance = (p->>'importance')::integer)
    AND (NOT (p ? 'dueBefore') OR s.due_at <= (p->>'dueBefore')::timestamptz)
    AND (NOT (p ? 'dueAfter') OR s.due_at >= (p->>'dueAfter')::timestamptz)
    AND (NOT (p ? 'updatedAfter') OR s.updated_at >= (p->>'updatedAfter')::timestamptz)
    AND (NOT (p ? 'minStability') OR s.fsrs_stability >= (p->>'minStability')::float8)
    AND (NOT (p ? 'maxDifficulty') OR s.fsrs_difficulty <= (p->>'maxDifficulty')::float8)
    AND (NOT (p ? 'maxRetrievability') OR v.retrievability <= (p->>'maxRetrievability')::float8)
  ), ordered AS (
    SELECT f.*, row_number() OVER (ORDER BY
      CASE WHEN p->>'direction'='asc' THEN CASE p->>'sort'
        WHEN 'title' THEN lower(title) END END ASC NULLS LAST,
      CASE WHEN p->>'direction'='desc' THEN CASE p->>'sort'
        WHEN 'title' THEN lower(title) END END DESC NULLS LAST,
      CASE WHEN p->>'direction'='asc' THEN CASE p->>'sort'
        WHEN 'dueAt' THEN "dueAt" WHEN 'createdAt' THEN "createdAt"
        WHEN 'updatedAt' THEN "updatedAt" WHEN 'lastReviewedAt' THEN "lastReviewedAt" END END ASC NULLS LAST,
      CASE WHEN p->>'direction'='desc' THEN CASE p->>'sort'
        WHEN 'dueAt' THEN "dueAt" WHEN 'createdAt' THEN "createdAt"
        WHEN 'updatedAt' THEN "updatedAt" WHEN 'lastReviewedAt' THEN "lastReviewedAt" END END DESC NULLS LAST,
      CASE WHEN p->>'direction'='asc' THEN CASE p->>'sort'
        WHEN 'importance' THEN importance WHEN 'reviewCount' THEN "reviewCount"
        WHEN 'fsrsStability' THEN "fsrsStability" WHEN 'fsrsDifficulty' THEN "fsrsDifficulty"
        WHEN 'retrievability' THEN retrievability END END ASC NULLS LAST,
      CASE WHEN p->>'direction'='desc' THEN CASE p->>'sort'
        WHEN 'importance' THEN importance WHEN 'reviewCount' THEN "reviewCount"
        WHEN 'fsrsStability' THEN "fsrsStability" WHEN 'fsrsDifficulty' THEN "fsrsDifficulty"
        WHEN 'retrievability' THEN retrievability END END DESC NULLS LAST, id ASC) AS position
    FROM filtered f
  ), page AS (SELECT * FROM ordered ORDER BY position LIMIT (p->>'limit')::int OFFSET (p->>'offset')::int),
  tags AS (
    SELECT tag, count(*) AS count FROM vision_memory_sheets s
    CROSS JOIN LATERAL (SELECT DISTINCT unnest(s.tags) AS tag) t
    WHERE CASE p->>'state' WHEN 'all' THEN true WHEN 'archived' THEN s.archived_at IS NOT NULL
      ELSE s.archived_at IS NULL END GROUP BY tag ORDER BY lower(tag)
  )
  SELECT jsonb_build_object(
    'sheets', COALESCE((SELECT jsonb_agg(to_jsonb(page)-'position' ORDER BY position) FROM page),'[]'),
    'total', (SELECT count(*) FROM filtered),
    'tags', COALESCE((SELECT jsonb_agg(to_jsonb(tags) ORDER BY lower(tag)) FROM tags),'[]'),
    'counts', (SELECT jsonb_build_object('active',count(*) FILTER (WHERE "archivedAt" IS NULL),
      'due',count(*) FILTER (WHERE "archivedAt" IS NULL AND "dueAt" <= now()),
      'new',count(*) FILTER (WHERE "archivedAt" IS NULL AND "reviewCount"=0),
      'archived',count(*) FILTER (WHERE "archivedAt" IS NOT NULL)) FROM vision_browser_sheets)) INTO result;
  RETURN result;
END $$;

CREATE OR REPLACE FUNCTION vision_web_get(p jsonb) RETURNS jsonb LANGUAGE sql AS $$
  WITH observations AS (
    SELECT o.id, o.outcome, COALESCE(c.note,o.note) AS note,
      COALESCE(c.context,o.context) AS context, o.reviewed_at AS "reviewedAt",
      o.next_review_at AS "nextReviewAt", o.rating, o.scheduling_applied AS "schedulingApplied",
      o.scheduler_version AS "schedulerVersion", o.desired_retention AS "desiredRetention",
      o.previous_stability AS "previousStability", o.previous_difficulty AS "previousDifficulty",
      o.new_stability AS "newStability", o.new_difficulty AS "newDifficulty",
      o.elapsed_days AS "elapsedDays", o.scheduled_days AS "scheduledDays",
      COALESCE(c.id,0) AS "correctionId", c.created_at AS "correctedAt",
      CASE WHEN c.id IS NOT NULL THEN jsonb_build_object('note',o.note,'context',o.context) END AS original
    FROM vision_memory_observations o
    LEFT JOIN LATERAL (SELECT * FROM vision_observation_corrections c
      WHERE c.observation_id=o.id ORDER BY c.id DESC LIMIT 1) c ON true
    WHERE o.sheet_id=(p->>'sheetId')::bigint ORDER BY o.reviewed_at DESC,o.id DESC
    LIMIT 50 OFFSET COALESCE((p->>'observationOffset')::int,0)
  )
  SELECT jsonb_build_object('found',true, 'sheet',to_jsonb(v)||jsonb_build_object('body',s.body),
    'observations',COALESCE((SELECT jsonb_agg(to_jsonb(o) ORDER BY "reviewedAt" DESC,id DESC) FROM observations o),'[]'),
    'observationTotal',(SELECT count(*) FROM vision_memory_observations WHERE sheet_id=s.id),
    'settings',(SELECT jsonb_build_object('modelVersion',model_version,'implementationVersion',implementation_version,
      'desiredRetention',desired_retention,'parameters',parameters) FROM vision_scheduler_settings),
    'edits',COALESCE((SELECT jsonb_agg(e ORDER BY e.id DESC) FROM
      (SELECT id,author,created_at AS "createdAt" FROM vision_sheet_edits WHERE sheet_id=s.id ORDER BY id DESC LIMIT 20) e),'[]'))
  FROM vision_browser_sheets v JOIN vision_memory_sheets s USING(id) WHERE s.id=(p->>'sheetId')::bigint
$$;

CREATE OR REPLACE FUNCTION vision_web_save(p jsonb, actor text) RETURNS jsonb LANGUAGE plpgsql AS $$
DECLARE oldrow vision_memory_sheets; newrow vision_memory_sheets;
  stability float8 := (p->>'fsrsStability')::float8;
  difficulty float8 := (p->>'fsrsDifficulty')::float8;
  assessed timestamptz := (p->>'fsrsLastReviewedAt')::timestamptz;
BEGIN
  IF (stability IS NULL) <> (difficulty IS NULL) OR (stability IS NULL) <> (assessed IS NULL)
     OR assessed > now() THEN RAISE EXCEPTION 'Invalid memory state' USING ERRCODE='22023'; END IF;
  IF p ? 'sheetId' THEN
    SELECT * INTO oldrow FROM vision_memory_sheets WHERE id=(p->>'sheetId')::bigint FOR UPDATE;
    IF NOT FOUND THEN RETURN jsonb_build_object('error','not_found'); END IF;
    IF oldrow.updated_at IS DISTINCT FROM (p->>'expectedUpdatedAt')::timestamptz THEN
      RETURN jsonb_build_object('error','conflict'); END IF;
    UPDATE vision_memory_sheets SET title=p->>'title',body=p->>'body',summary=p->>'summary',
      tags=ARRAY(SELECT jsonb_array_elements_text(p->'tags')),
      aliases=ARRAY(SELECT jsonb_array_elements_text(p->'aliases')),
      importance=(p->>'importance')::smallint,due_at=(p->>'dueAt')::timestamptz,
      fsrs_stability=stability,fsrs_difficulty=difficulty,fsrs_last_reviewed_at=assessed,
      fsrs_model_version=CASE WHEN stability IS NULL THEN NULL ELSE (SELECT model_version FROM vision_scheduler_settings) END,
      archived_at=CASE WHEN (p->>'archived')::boolean THEN COALESCE(archived_at,now()) ELSE NULL END,
      updated_at=clock_timestamp() WHERE id=oldrow.id RETURNING * INTO newrow;
  ELSE
    INSERT INTO vision_memory_sheets(title,body,summary,tags,aliases,importance,due_at,
      fsrs_stability,fsrs_difficulty,fsrs_last_reviewed_at,fsrs_model_version,archived_at)
    VALUES(p->>'title',p->>'body',p->>'summary',ARRAY(SELECT jsonb_array_elements_text(p->'tags')),
      ARRAY(SELECT jsonb_array_elements_text(p->'aliases')),(p->>'importance')::smallint,(p->>'dueAt')::timestamptz,
      stability,difficulty,assessed,CASE WHEN stability IS NOT NULL THEN (SELECT model_version FROM vision_scheduler_settings) END,
      CASE WHEN (p->>'archived')::boolean THEN now() END) RETURNING * INTO newrow;
  END IF;
  INSERT INTO vision_sheet_edits(sheet_id,author,before_value,after_value)
    VALUES(newrow.id,actor,CASE WHEN oldrow.id IS NOT NULL THEN to_jsonb(oldrow) END,to_jsonb(newrow));
  RETURN jsonb_build_object('saved',true,'sheetId',newrow.id);
END $$;

CREATE OR REPLACE FUNCTION vision_web_correct(p jsonb, actor text) RETURNS jsonb LANGUAGE plpgsql AS $$
DECLARE target vision_memory_observations; latest bigint;
BEGIN
  SELECT * INTO target FROM vision_memory_observations WHERE id=(p->>'observationId')::bigint FOR UPDATE;
  IF NOT FOUND THEN RETURN jsonb_build_object('error','not_found'); END IF;
  SELECT COALESCE(max(id),0) INTO latest FROM vision_observation_corrections WHERE observation_id=target.id;
  IF latest <> (p->>'expectedCorrectionId')::bigint THEN RETURN jsonb_build_object('error','conflict'); END IF;
  INSERT INTO vision_observation_corrections(observation_id,note,context,author)
    VALUES(target.id,p->>'note',p->'context',actor);
  RETURN jsonb_build_object('saved',true,'sheetId',target.sheet_id);
END $$;

INSERT INTO vision_schema_migrations(version) VALUES(4) ON CONFLICT DO NOTHING;
COMMIT;
