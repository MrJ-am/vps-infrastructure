CREATE TABLE IF NOT EXISTS schema_migrations(version integer PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS comptes (
  id uuid PRIMARY KEY,
  pseudonyme text UNIQUE NOT NULL CHECK (length(pseudonyme) BETWEEN 3 AND 40),
  password_hash text NOT NULL,
  auth_recovery_hash text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  last_seen timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS sessions (
  token_hash text PRIMARY KEY,
  compte uuid NOT NULL REFERENCES comptes(id) ON DELETE CASCADE,
  csrf text NOT NULL,
  expires_at timestamptz NOT NULL,
  last_seen timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS coffres (
  compte uuid PRIMARY KEY REFERENCES comptes(id) ON DELETE CASCADE,
  revision bigint NOT NULL DEFAULT 1,
  payload jsonb NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS objets (
  compte uuid NOT NULL REFERENCES comptes(id) ON DELETE CASCADE,
  id uuid NOT NULL,
  payload jsonb NOT NULL,
  PRIMARY KEY(compte, id)
);
-- Tombstones techniques : réappliquer avant de rouvrir une sauvegarde restaurée.
CREATE TABLE IF NOT EXISTS suppressions (
  compte uuid PRIMARY KEY,
  deleted_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS archives (
  id uuid PRIMARY KEY,
  compte uuid NOT NULL REFERENCES comptes(id) ON DELETE CASCADE,
  payload jsonb NOT NULL,
  images jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
INSERT INTO schema_migrations(version) VALUES (1) ON CONFLICT DO NOTHING;
