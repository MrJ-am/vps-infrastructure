-- Base du journal exclusivement. Aucun fichier ni compte de production lu ici.
-- vision_journal_import est une identité opérateur temporaire, distincte du writer.
BEGIN;
CREATE TABLE vision_effacements.fermetures (
 sujet text PRIMARY KEY CHECK(sujet ~ '^[A-Za-z0-9_.-]{1,64}$'),
 emetteur text NOT NULL DEFAULT 'https://log.mrj.am/realms/mrjam'
   CHECK(emetteur='https://log.mrj.am/realms/mrjam'),
 demande_a timestamptz NOT NULL
);
ALTER TABLE vision_effacements.fermetures OWNER TO vision_journal_owner;
CREATE FUNCTION vision_effacements.importer_historique(u text,date_unix bigint) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,vision_effacements,pg_temp AS $$
BEGIN
 IF date_unix<=0 OR date_unix>extract(epoch FROM clock_timestamp())+300
   THEN RAISE EXCEPTION 'registre_invalide'; END IF;
 INSERT INTO vision_effacements.demandes(utilisateur,demande_a)
 VALUES(u,to_timestamp(date_unix)) ON CONFLICT(utilisateur) DO UPDATE
 SET demande_a=least(demandes.demande_a,excluded.demande_a),
 -- Une date plus ancienne impose de réarchiver le registre complet.
 archive_confirmee_a=CASE WHEN excluded.demande_a<demandes.demande_a THEN NULL ELSE demandes.archive_confirmee_a END;
END $$;
CREATE FUNCTION vision_effacements.importer_fermeture(s text,date_unix bigint) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,vision_effacements,pg_temp AS $$
BEGIN
 IF date_unix<=0 OR date_unix>extract(epoch FROM clock_timestamp())+300
   THEN RAISE EXCEPTION 'registre_invalide'; END IF;
 INSERT INTO vision_effacements.fermetures(sujet,demande_a) VALUES(s,to_timestamp(date_unix))
 ON CONFLICT(sujet) DO UPDATE SET demande_a=least(fermetures.demande_a,excluded.demande_a);
END $$;
ALTER FUNCTION vision_effacements.importer_historique(text,bigint) OWNER TO vision_journal_owner;
ALTER FUNCTION vision_effacements.importer_fermeture(text,bigint) OWNER TO vision_journal_owner;
REVOKE ALL ON ALL TABLES IN SCHEMA vision_effacements FROM PUBLIC,vision_journal_writer,vision_journal_import;
REVOKE ALL ON FUNCTION vision_effacements.importer_historique(text,bigint),
 vision_effacements.importer_fermeture(text,bigint) FROM PUBLIC,vision_journal_writer;
GRANT USAGE ON SCHEMA vision_effacements TO vision_journal_import;
GRANT EXECUTE ON FUNCTION vision_effacements.importer_historique(text,bigint),
 vision_effacements.importer_fermeture(text,bigint) TO vision_journal_import;
COMMIT;
