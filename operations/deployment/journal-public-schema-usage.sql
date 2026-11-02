-- Explicit post-bootstrap correction. The historical journal sources stay exact.
-- Namespace lookup is needed by the closed catalogue checks, including the
-- deliberate absence of public.vision_schema_migrations in this dedicated DB.
BEGIN;
DO $$
BEGIN
 IF current_database()<>'vision_journal'
 THEN RAISE EXCEPTION 'journal_namespace_database_refused'; END IF;
END $$;
GRANT USAGE ON SCHEMA public TO vision_journal_writer,
 vision_journal_archiviste,vision_journal_rejeu,vision_journal_fermeture;
COMMIT;
