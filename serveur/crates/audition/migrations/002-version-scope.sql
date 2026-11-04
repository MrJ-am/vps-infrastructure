-- Additive hardening of the exact retained 001 schema. Run explicitly through
-- the reviewed migrator, never from the application startup. No production run
-- is implied by the local synthetic qualification.
BEGIN;
DROP POLICY versions_lecture ON audition.versions;
CREATE POLICY versions_lecture ON audition.versions FOR SELECT USING (
 EXISTS (SELECT 1 FROM audition.objets o WHERE o.id=objet AND o.groupe=versions.groupe)
);
DROP POLICY versions_insertion ON audition.versions;
CREATE POLICY versions_insertion ON audition.versions FOR INSERT WITH CHECK (
 auteur=current_setting('audition.acteur',true) AND
 EXISTS (SELECT 1 FROM audition.objets o WHERE o.id=objet AND o.groupe=versions.groupe AND
  (audition.role_groupe(o.groupe)='enseignant' OR
   (o.nature='seance' AND o.document->>'eleve'=current_setting('audition.acteur',true))))
);
INSERT INTO audition.schema_migrations VALUES(2);
COMMIT;
