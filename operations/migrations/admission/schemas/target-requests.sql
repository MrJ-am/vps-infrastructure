-- Colonnes historiques préservées. reservation est un état supplémentaire
-- interne ; aucune confirmation ni création IdP avant la réservation effective.
CREATE TABLE IF NOT EXISTS demandes (
 id TEXT PRIMARY KEY, invitation TEXT NOT NULL, notice TEXT NOT NULL,
 courriel TEXT NOT NULL, pays TEXT NOT NULL, age TEXT NOT NULL,
 parent TEXT NOT NULL, pseudonyme TEXT NOT NULL, parental INTEGER NOT NULL,
 manuel INTEGER NOT NULL, verification TEXT UNIQUE, accord TEXT UNIQUE,
 verifie_a INTEGER, accord_a INTEGER, controle_a INTEGER,
 methode TEXT, reference TEXT, source_pays TEXT,
 sujet TEXT, nouvel_utilisateur INTEGER NOT NULL DEFAULT 0,
 etat TEXT NOT NULL DEFAULT 'attente', cree INTEGER NOT NULL, expire INTEGER NOT NULL,
 terminee INTEGER
);
CREATE INDEX IF NOT EXISTS demandes_courriel ON demandes(courriel,cree);
