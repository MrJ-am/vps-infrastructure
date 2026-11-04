-- Explicit namespace access for the existing, isolated Rust administration role.
-- No object privilege, role membership, schema creation or ownership changes.
BEGIN;
DO $$
BEGIN
 IF current_database()<>'vision'
 THEN RAISE EXCEPTION 'vision_admin_namespace_database_refused'; END IF;
END $$;
GRANT USAGE ON SCHEMA public TO vision_administration;
COMMIT;
