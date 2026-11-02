-- À appliquer exclusivement dans une base dédiée, hors restauration Vision.
-- Le rôle écrivain n'a aucune lecture, modification ni suppression de ligne.
BEGIN;
CREATE SCHEMA vision_effacements AUTHORIZATION vision_journal_owner;
CREATE TABLE vision_effacements.demandes (
 utilisateur text PRIMARY KEY CHECK (utilisateur ~ '^[A-Za-z0-9_.-]{1,64}$'),
 demande_a timestamptz NOT NULL DEFAULT clock_timestamp(),
 -- Ce champ reste fermé au rôle applicatif. Seul un archiviste séparé peut
 -- attester l'acceptation du registre chiffré par le relais externe qualifié.
 archive_confirmee_a timestamptz
);
ALTER TABLE vision_effacements.demandes OWNER TO vision_journal_owner;
CREATE FUNCTION vision_effacements.enregistrer(u text) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,vision_effacements,pg_temp AS $$
BEGIN
 INSERT INTO vision_effacements.demandes(utilisateur) VALUES(u) ON CONFLICT DO NOTHING;
 RETURN (SELECT archive_confirmee_a IS NOT NULL FROM vision_effacements.demandes WHERE utilisateur=u);
END
$$;
ALTER FUNCTION vision_effacements.enregistrer(text) OWNER TO vision_journal_owner;
REVOKE ALL ON SCHEMA vision_effacements FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA vision_effacements FROM PUBLIC,vision_journal_writer;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA vision_effacements FROM PUBLIC;
GRANT USAGE ON SCHEMA vision_effacements TO vision_journal_writer;
GRANT EXECUTE ON FUNCTION vision_effacements.enregistrer(text) TO vision_journal_writer;
COMMIT;
