BEGIN;

CREATE TABLE IF NOT EXISTS vision_memory_sheets (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  title text NOT NULL CHECK (char_length(title) BETWEEN 1 AND 200),
  body text NOT NULL CHECK (char_length(body) BETWEEN 1 AND 50000),
  summary text NOT NULL DEFAULT '' CHECK (char_length(summary) <= 2000),
  tags text[] NOT NULL DEFAULT '{}',
  aliases text[] NOT NULL DEFAULT '{}',
  importance smallint NOT NULL DEFAULT 3 CHECK (importance BETWEEN 1 AND 5),
  due_at timestamptz DEFAULT now(),
  last_reviewed_at timestamptz,
  last_outcome text CHECK (
    last_outcome IS NULL OR
    last_outcome IN ('recalled', 'partial', 'forgotten', 'not_assessed')
  ),
  review_count integer NOT NULL DEFAULT 0 CHECK (review_count >= 0),
  archived_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (cardinality(tags) <= 50),
  CHECK (cardinality(aliases) <= 50)
);

CREATE TABLE IF NOT EXISTS vision_memory_observations (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  sheet_id bigint NOT NULL REFERENCES vision_memory_sheets(id) ON DELETE CASCADE,
  outcome text NOT NULL CHECK (
    outcome IN ('recalled', 'partial', 'forgotten', 'not_assessed')
  ),
  note text NOT NULL CHECK (char_length(note) BETWEEN 1 AND 4000),
  context jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(context) = 'object'),
  reviewed_at timestamptz NOT NULL DEFAULT now(),
  next_review_at timestamptz
);

CREATE INDEX IF NOT EXISTS vision_memory_sheets_due_idx
  ON vision_memory_sheets (due_at, importance DESC)
  WHERE archived_at IS NULL AND due_at IS NOT NULL;

CREATE INDEX IF NOT EXISTS vision_memory_sheets_text_idx
  ON vision_memory_sheets USING gin (
    to_tsvector('simple'::regconfig, title || ' ' || summary || ' ' || body)
  );

CREATE INDEX IF NOT EXISTS vision_memory_observations_sheet_reviewed_idx
  ON vision_memory_observations (sheet_id, reviewed_at DESC, id DESC);

INSERT INTO vision_schema_migrations (version)
VALUES (2)
ON CONFLICT (version) DO NOTHING;

COMMIT;
