CREATE TABLE IF NOT EXISTS courriels (
                cle TEXT PRIMARY KEY, message BLOB NOT NULL, cree INTEGER NOT NULL,
                etat TEXT NOT NULL DEFAULT 'attente', essais INTEGER NOT NULL DEFAULT 0,
                prochain INTEGER NOT NULL DEFAULT 0, accepte INTEGER, erreur TEXT)
