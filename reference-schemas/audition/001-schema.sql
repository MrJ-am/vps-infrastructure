-- Migration centrale explicite, dans la base métier Vision existante.
-- Propriétaire/migrateur distincts du login audition_app ; pas d'accès Vision.
BEGIN;
CREATE SCHEMA audition;
REVOKE ALL ON SCHEMA audition FROM PUBLIC;
CREATE TABLE audition.schema_migrations(version integer PRIMARY KEY);
CREATE TABLE audition.administrateurs(acteur text PRIMARY KEY CHECK(acteur ~ '^[A-Za-z0-9_.-]{1,64}$'), actif boolean NOT NULL DEFAULT true);
CREATE TABLE audition.groupes(id text PRIMARY KEY, nom text NOT NULL CHECK(length(nom) BETWEEN 1 AND 200));
CREATE TABLE audition.membres(groupe text REFERENCES audition.groupes ON DELETE CASCADE, acteur text NOT NULL CHECK(acteur ~ '^[A-Za-z0-9_.-]{1,64}$'),
 role text NOT NULL CHECK(role IN ('enseignant','eleve')), PRIMARY KEY(groupe,acteur));
CREATE TABLE audition.objets(id text PRIMARY KEY, groupe text NOT NULL REFERENCES audition.groupes ON DELETE CASCADE,
 nature text NOT NULL CHECK(nature IN ('cours','activite','affectation','seance','remediation')), revision bigint NOT NULL CHECK(revision>0),
 document jsonb NOT NULL CHECK(jsonb_typeof(document)='object' AND octet_length(document::text)<=1048576), modifie_a timestamptz NOT NULL);
CREATE INDEX objets_groupe_nature ON audition.objets(groupe,nature,id);
CREATE UNIQUE INDEX une_seance_par_affectation_eleve ON audition.objets(groupe,(document->>'affectation'),(document->>'eleve')) WHERE nature='seance';
CREATE TABLE audition.versions(objet text REFERENCES audition.objets ON DELETE CASCADE, groupe text NOT NULL REFERENCES audition.groupes ON DELETE CASCADE,
 revision bigint NOT NULL, document jsonb NOT NULL, auteur text NOT NULL, recu_a timestamptz NOT NULL, PRIMARY KEY(objet,revision));
CREATE TABLE audition.requetes(acteur text NOT NULL, cle text NOT NULL, groupe text REFERENCES audition.groupes ON DELETE CASCADE,
 operation text NOT NULL, empreinte text NOT NULL, resultat jsonb NOT NULL, recu_a timestamptz NOT NULL, PRIMARY KEY(acteur,cle));
CREATE TABLE audition.audit(id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, groupe text, auteur text NOT NULL,
 operation text NOT NULL, cible text NOT NULL, recu_a timestamptz NOT NULL, details jsonb NOT NULL DEFAULT '{}'::jsonb);

-- Fonctions de droits à propriétaire distinct, search_path fermé. Pas de contenu
-- pédagogique dans les habilitations. La session applicative fournit l'acteur
-- seulement après vérification Log ; set_config n'est pas une authentification.
CREATE FUNCTION audition.est_admin() RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
 SELECT EXISTS(SELECT FROM audition.administrateurs WHERE acteur=current_setting('audition.acteur',true) AND actif)
$$;
CREATE FUNCTION audition.role_groupe(g text) RETURNS text LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
 SELECT role FROM audition.membres WHERE groupe=g AND acteur=current_setting('audition.acteur',true)
$$;
REVOKE ALL ON FUNCTION audition.est_admin(),audition.role_groupe(text) FROM PUBLIC;

ALTER TABLE audition.groupes ENABLE ROW LEVEL SECURITY;
ALTER TABLE audition.groupes FORCE ROW LEVEL SECURITY;
CREATE POLICY groupes_lecture ON audition.groupes FOR SELECT USING(audition.est_admin() OR audition.role_groupe(id) IS NOT NULL);
CREATE POLICY groupes_creation ON audition.groupes FOR INSERT WITH CHECK(audition.est_admin());
CREATE POLICY groupes_suppression ON audition.groupes FOR DELETE USING(audition.est_admin());
ALTER TABLE audition.objets ENABLE ROW LEVEL SECURITY;
ALTER TABLE audition.objets FORCE ROW LEVEL SECURITY;
-- Un administrateur technique sans rattachement ne lit aucune production.
CREATE POLICY objets_lecture ON audition.objets FOR SELECT USING(
 audition.role_groupe(groupe)='enseignant' OR (audition.role_groupe(groupe)='eleve' AND
 ((nature IN ('cours','activite')) OR (nature='seance' AND document->>'eleve'=current_setting('audition.acteur',true)) OR
 (nature IN ('affectation','remediation') AND document->'eleves' ? current_setting('audition.acteur',true)))));
CREATE POLICY objets_insertion ON audition.objets FOR INSERT WITH CHECK(
 audition.role_groupe(groupe)='enseignant' OR (audition.role_groupe(groupe)='eleve' AND nature='seance' AND document->>'eleve'=current_setting('audition.acteur',true)));
CREATE POLICY objets_modification ON audition.objets FOR UPDATE USING(
 audition.role_groupe(groupe)='enseignant' OR (audition.role_groupe(groupe)='eleve' AND nature='seance' AND document->>'eleve'=current_setting('audition.acteur',true))) WITH CHECK(
 audition.role_groupe(groupe)='enseignant' OR (audition.role_groupe(groupe)='eleve' AND nature='seance' AND document->>'eleve'=current_setting('audition.acteur',true)));
ALTER TABLE audition.versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE audition.versions FORCE ROW LEVEL SECURITY;
CREATE POLICY versions_lecture ON audition.versions FOR SELECT USING(audition.role_groupe(groupe) IS NOT NULL);
CREATE POLICY versions_insertion ON audition.versions FOR INSERT WITH CHECK(audition.role_groupe(groupe) IS NOT NULL AND auteur=current_setting('audition.acteur',true));
ALTER TABLE audition.requetes ENABLE ROW LEVEL SECURITY;
ALTER TABLE audition.requetes FORCE ROW LEVEL SECURITY;
CREATE POLICY requetes_propres ON audition.requetes USING(acteur=current_setting('audition.acteur',true)) WITH CHECK(acteur=current_setting('audition.acteur',true));
-- membres/administrateurs restent des métadonnées de droits ; les fonctions
-- SECURITY DEFINER évitent la récursion RLS et ne retournent aucun contenu.
ALTER TABLE audition.membres ENABLE ROW LEVEL SECURITY;
CREATE POLICY membres_lecture ON audition.membres FOR SELECT USING(audition.est_admin() OR audition.role_groupe(groupe)='enseignant' OR acteur=current_setting('audition.acteur',true));
CREATE POLICY membres_insertion ON audition.membres FOR INSERT WITH CHECK(audition.est_admin());
CREATE POLICY membres_modification ON audition.membres FOR UPDATE USING(audition.est_admin()) WITH CHECK(audition.est_admin());
CREATE POLICY membres_suppression ON audition.membres FOR DELETE USING(audition.est_admin());
ALTER TABLE audition.administrateurs ENABLE ROW LEVEL SECURITY;
CREATE POLICY administrateurs_propres ON audition.administrateurs FOR SELECT USING(acteur=current_setting('audition.acteur',true));
ALTER TABLE audition.audit ENABLE ROW LEVEL SECURITY;
ALTER TABLE audition.audit FORCE ROW LEVEL SECURITY;
CREATE POLICY audit_insertion ON audition.audit FOR INSERT WITH CHECK(auteur=current_setting('audition.acteur',true));
CREATE POLICY audit_admin ON audition.audit FOR SELECT USING(audition.est_admin());
INSERT INTO audition.schema_migrations VALUES(1);
COMMIT;
