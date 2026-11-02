-- Order is part of the cursor protocol: compare ASCII identifiers identically
-- in PostgreSQL and Rust, independently of the database locale. No data rewrite.
BEGIN;
CREATE OR REPLACE FUNCTION vision_effacements.lire_rejeu(apres text) RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,vision_effacements,pg_temp AS $$
 SELECT coalesce(jsonb_agg(ligne ORDER BY cle COLLATE "C"),'[]'::jsonb) FROM (
  SELECT * FROM (
   SELECT 'v:'||utilisateur cle,jsonb_build_object('cle','v:'||utilisateur,'type','vision','utilisateur',utilisateur) ligne FROM demandes WHERE archive_confirmee_a IS NOT NULL AND archive_sha256 IS NOT NULL
   UNION ALL
   SELECT 'f:'||sujet,jsonb_build_object('cle','f:'||sujet,'type','fermeture_commune','sujet',sujet,'emetteur',emetteur,'outils',jsonb_build_object('vision',comptes)) FROM fermetures WHERE archive_confirmee_a IS NOT NULL AND archive_sha256 IS NOT NULL
  ) p WHERE cle COLLATE "C">apres COLLATE "C" ORDER BY cle COLLATE "C" LIMIT 100
 ) q
$$;
CREATE OR REPLACE FUNCTION vision_effacements.prochains_rejeux() RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,vision_effacements,pg_temp AS $$
 SELECT coalesce(jsonb_agg(ligne ORDER BY cle COLLATE "C"),'[]'::jsonb) FROM (
  SELECT * FROM (
   SELECT 'v:'||utilisateur cle,jsonb_build_object('cle','v:'||utilisateur,'type','vision','utilisateur',utilisateur,'archive_sha256',archive_sha256) ligne
    FROM demandes WHERE archive_confirmee_a IS NOT NULL AND archive_sha256 IS NOT NULL AND applique_sha256 IS DISTINCT FROM archive_sha256
   UNION ALL
   SELECT 'f:'||sujet,jsonb_build_object('cle','f:'||sujet,'type','fermeture_commune','sujet',sujet,'emetteur',emetteur,'outils',jsonb_build_object('vision',comptes),'archive_sha256',archive_sha256)
    FROM fermetures WHERE archive_confirmee_a IS NOT NULL AND archive_sha256 IS NOT NULL AND applique_sha256 IS DISTINCT FROM archive_sha256
     AND demande_a<=clock_timestamp()-interval '120 seconds'
  ) p ORDER BY cle COLLATE "C" LIMIT 100
 ) q
$$;
-- CREATE OR REPLACE preserves owners and EXECUTE grants from migration 003.
COMMIT;
