-- Nouvelle étape explicite. Aucun événement, condensat ou acquittement réécrit.
-- Les signatures historiques continuent de désigner exclusivement leur issuer.
BEGIN;
ALTER TABLE vision_effacements.fermetures DROP CONSTRAINT fermetures_emetteur_check;
ALTER TABLE vision_effacements.fermetures ADD CONSTRAINT fermetures_emetteur_check
 CHECK(emetteur IN ('https://log.mrj.am/realms/mrjam',
                   'https://log.mrj.am/oauth2/openid/mrjam-vision'));
CREATE OR REPLACE FUNCTION vision_effacements.importer_fermeture(s text,e text,date_unix bigint,c jsonb) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,vision_effacements,pg_temp AS $$
DECLARE ensemble jsonb;
BEGIN
 IF e IS NULL OR e NOT IN ('https://log.mrj.am/realms/mrjam','https://log.mrj.am/oauth2/openid/mrjam-vision')
   OR date_unix IS NULL OR date_unix<=0 OR date_unix>extract(epoch FROM clock_timestamp())+300
 THEN RAISE EXCEPTION 'registre_invalide'; END IF;
 PERFORM verifier_comptes(c);
 PERFORM 1 FROM vision_effacements.revision WHERE singleton FOR UPDATE;
 -- Le PK historique reste inchangé ; collision entre fournisseurs = refus.
 IF EXISTS(SELECT FROM fermetures WHERE sujet=s AND emetteur<>e)
 THEN RAISE EXCEPTION 'registre_invalide'; END IF;
 SELECT coalesce(jsonb_agg(u ORDER BY u),'[]'::jsonb) INTO ensemble FROM
   (SELECT DISTINCT value u FROM jsonb_array_elements(c||coalesce((SELECT comptes FROM fermetures WHERE sujet=s),'[]'::jsonb))) q;
 PERFORM verifier_comptes(ensemble);
 INSERT INTO fermetures(sujet,emetteur,demande_a,comptes) VALUES(s,e,to_timestamp(date_unix),ensemble)
 ON CONFLICT(sujet) DO UPDATE SET demande_a=least(fermetures.demande_a,excluded.demande_a),comptes=excluded.comptes,
 archive_confirmee_a=CASE WHEN excluded.demande_a<fermetures.demande_a OR excluded.comptes<>fermetures.comptes THEN NULL ELSE fermetures.archive_confirmee_a END,
 archive_sha256=CASE WHEN excluded.demande_a<fermetures.demande_a OR excluded.comptes<>fermetures.comptes THEN NULL ELSE fermetures.archive_sha256 END;
END $$;
ALTER FUNCTION vision_effacements.importer_fermeture(text,text,bigint,jsonb) OWNER TO vision_journal_owner;
CREATE OR REPLACE FUNCTION vision_effacements.importer_fermeture(s text,date_unix bigint,c jsonb) RETURNS void
LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,vision_effacements,pg_temp AS $$
 SELECT importer_fermeture(s,'https://log.mrj.am/realms/mrjam',date_unix,c)
$$;
CREATE OR REPLACE FUNCTION vision_effacements.importer_fermeture(s text,date_unix bigint) RETURNS void
LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,vision_effacements,pg_temp AS $$
 SELECT importer_fermeture(s,'https://log.mrj.am/realms/mrjam',date_unix,'[]'::jsonb)
$$;
CREATE OR REPLACE FUNCTION vision_effacements.consigner_fermeture(s text,e text,c jsonb) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,vision_effacements,pg_temp AS $$
BEGIN
 PERFORM importer_fermeture(s,e,floor(extract(epoch FROM clock_timestamp()))::bigint,c);
 RETURN (SELECT archive_confirmee_a IS NOT NULL FROM fermetures WHERE sujet=s AND emetteur=e);
END $$;
REVOKE ALL ON FUNCTION vision_effacements.importer_fermeture(text,text,bigint,jsonb)
 FROM PUBLIC,vision_journal_writer,vision_journal_archiviste,vision_journal_rejeu,vision_journal_fermeture;
GRANT EXECUTE ON FUNCTION vision_effacements.importer_fermeture(text,text,bigint,jsonb) TO vision_journal_import;
-- CREATE OR REPLACE conserve propriétaires et droits des signatures historiques.
COMMIT;
