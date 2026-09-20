BEGIN;

CREATE TABLE IF NOT EXISTS vision_scheduler_settings (
  singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
  model_version text NOT NULL,
  implementation_version text NOT NULL,
  source_commit text NOT NULL CHECK (source_commit ~ '^[0-9a-f]{40}$'),
  desired_retention double precision NOT NULL
    CHECK (desired_retention > 0.0 AND desired_retention < 1.0),
  parameters double precision[] NOT NULL CHECK (cardinality(parameters) = 21),
  updated_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO vision_scheduler_settings
  (singleton, model_version, implementation_version, source_commit,
   desired_retention, parameters)
VALUES
  (true, 'fsrs-6', 'fsrs-rs-6.6.2',
   '6088949b99d44f46f5328fd7289d209b9a842b68', 0.9,
   ARRAY[
     0.212, 1.2931, 2.3065, 8.2956, 6.4133, 0.8334, 3.0194,
     0.001, 1.8722, 0.1666, 0.796, 1.4835, 0.0614, 0.2629,
     1.6483, 0.6014, 1.8729, 0.5425, 0.0912, 0.0658, 0.1542
   ]::double precision[])
ON CONFLICT (singleton) DO NOTHING;

ALTER TABLE vision_memory_sheets
  ADD COLUMN IF NOT EXISTS fsrs_stability double precision
    CHECK (fsrs_stability BETWEEN 0.001 AND 36500.0),
  ADD COLUMN IF NOT EXISTS fsrs_difficulty double precision
    CHECK (fsrs_difficulty BETWEEN 1.0 AND 10.0),
  ADD COLUMN IF NOT EXISTS fsrs_last_reviewed_at timestamptz,
  ADD COLUMN IF NOT EXISTS fsrs_review_count integer NOT NULL DEFAULT 0
    CHECK (fsrs_review_count >= 0),
  ADD COLUMN IF NOT EXISTS fsrs_model_version text;

ALTER TABLE vision_memory_observations
  ADD COLUMN IF NOT EXISTS rating smallint CHECK (rating BETWEEN 1 AND 4),
  ADD COLUMN IF NOT EXISTS scheduling_applied boolean NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS scheduler_version text,
  ADD COLUMN IF NOT EXISTS desired_retention double precision
    CHECK (desired_retention > 0.0 AND desired_retention < 1.0),
  ADD COLUMN IF NOT EXISTS previous_stability double precision,
  ADD COLUMN IF NOT EXISTS previous_difficulty double precision,
  ADD COLUMN IF NOT EXISTS new_stability double precision,
  ADD COLUMN IF NOT EXISTS new_difficulty double precision,
  ADD COLUMN IF NOT EXISTS elapsed_days integer CHECK (elapsed_days >= 0),
  ADD COLUMN IF NOT EXISTS scheduled_days integer CHECK (scheduled_days >= 1);

CREATE INDEX IF NOT EXISTS vision_memory_observations_scheduled_idx
  ON vision_memory_observations (sheet_id, reviewed_at DESC, id DESC)
  WHERE scheduling_applied;

INSERT INTO vision_schema_migrations (version)
VALUES (3)
ON CONFLICT (version) DO NOTHING;

COMMIT;
