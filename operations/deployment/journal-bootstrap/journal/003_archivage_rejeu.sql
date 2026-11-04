-- Base privée du journal ; aucune donnée de contenu ni secret dans le store.
BEGIN;
ALTER TABLE vision_effacements.demandes ADD COLUMN archive_sha256 text CHECK(archive_sha256 ~ '^[a-f0-9]{64}$');
ALTER TABLE vision_effacements.demandes ADD COLUMN applique_sha256 text CHECK(applique_sha256 ~ '^[a-f0-9]{64}$');
-- Une ancienne date d'acquittement sans empreinte de l'archive ne constitue
-- pas une preuve suffisante pour les nouveaux workers : réarchiver d'abord.
UPDATE vision_effacements.demandes SET archive_confirmee_a=NULL WHERE archive_confirmee_a IS NOT NULL;
ALTER TABLE vision_effacements.fermetures ADD COLUMN comptes jsonb NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE vision_effacements.fermetures ADD COLUMN archive_confirmee_a timestamptz;
ALTER TABLE vision_effacements.fermetures ADD COLUMN archive_sha256 text CHECK(archive_sha256 ~ '^[a-f0-9]{64}$');
ALTER TABLE vision_effacements.fermetures ADD COLUMN applique_sha256 text CHECK(applique_sha256 ~ '^[a-f0-9]{64}$');
CREATE TABLE vision_effacements.revision(singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),numero bigint NOT NULL DEFAULT 0);
ALTER TABLE vision_effacements.revision OWNER TO vision_journal_owner;
INSERT INTO vision_effacements.revision(singleton) VALUES(true);
CREATE FUNCTION vision_effacements.avancer_revision() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,vision_effacements,pg_temp AS $$
BEGIN UPDATE vision_effacements.revision SET numero=numero+1 WHERE singleton; RETURN NULL; END $$;
ALTER FUNCTION vision_effacements.avancer_revision() OWNER TO vision_journal_owner;
CREATE TRIGGER revision_demandes AFTER INSERT OR UPDATE ON vision_effacements.demandes FOR EACH STATEMENT EXECUTE FUNCTION vision_effacements.avancer_revision();
CREATE TRIGGER revision_fermetures AFTER INSERT OR UPDATE ON vision_effacements.fermetures FOR EACH STATEMENT EXECUTE FUNCTION vision_effacements.avancer_revision();
CREATE FUNCTION vision_effacements.verifier_comptes(c jsonb) RETURNS void
LANGUAGE plpgsql IMMUTABLE AS $$
BEGIN
 IF c IS NULL OR jsonb_typeof(c)<>'array' OR jsonb_array_length(c)>10 OR EXISTS(SELECT FROM jsonb_array_elements(c) u
  WHERE jsonb_typeof(u)<>'string' OR NOT (u#>>'{}') ~ '^[A-Za-z0-9_.-]{1,64}$')
 THEN RAISE EXCEPTION 'registre_invalide'; END IF;
END $$;
ALTER FUNCTION vision_effacements.verifier_comptes(jsonb) OWNER TO vision_journal_owner;
CREATE FUNCTION vision_effacements.importer_fermeture(s text,date_unix bigint,c jsonb) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,vision_effacements,pg_temp AS $$
DECLARE ensemble jsonb;
BEGIN
 PERFORM verifier_comptes(c);
 IF date_unix IS NULL OR date_unix<=0 OR date_unix>extract(epoch FROM clock_timestamp())+300 THEN RAISE EXCEPTION 'registre_invalide'; END IF;
 PERFORM 1 FROM vision_effacements.revision WHERE singleton FOR UPDATE;
 SELECT coalesce(jsonb_agg(u ORDER BY u),'[]'::jsonb) INTO ensemble FROM
   (SELECT DISTINCT value u FROM jsonb_array_elements(c||coalesce((SELECT comptes FROM fermetures WHERE sujet=s),'[]'::jsonb))) q;
 PERFORM verifier_comptes(ensemble);
 INSERT INTO fermetures(sujet,demande_a,comptes) VALUES(s,to_timestamp(date_unix),ensemble)
 ON CONFLICT(sujet) DO UPDATE SET demande_a=least(fermetures.demande_a,excluded.demande_a),comptes=excluded.comptes,
 archive_confirmee_a=CASE WHEN excluded.demande_a<fermetures.demande_a OR excluded.comptes<>fermetures.comptes THEN NULL ELSE fermetures.archive_confirmee_a END,
 archive_sha256=CASE WHEN excluded.demande_a<fermetures.demande_a OR excluded.comptes<>fermetures.comptes THEN NULL ELSE fermetures.archive_sha256 END;
END $$;
ALTER FUNCTION vision_effacements.importer_fermeture(text,bigint,jsonb) OWNER TO vision_journal_owner;
CREATE FUNCTION vision_effacements.consigner_fermeture(s text,e text,c jsonb) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,vision_effacements,pg_temp AS $$
BEGIN
 IF e IS NULL OR e<>'https://log.mrj.am/realms/mrjam' THEN RAISE EXCEPTION 'registre_invalide'; END IF;
 PERFORM importer_fermeture(s,floor(extract(epoch FROM clock_timestamp()))::bigint,c);
 RETURN (SELECT archive_confirmee_a IS NOT NULL FROM fermetures WHERE sujet=s);
END $$;
ALTER FUNCTION vision_effacements.consigner_fermeture(text,text,jsonb) OWNER TO vision_journal_owner;
CREATE FUNCTION vision_effacements.prochaines_archives() RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,vision_effacements,pg_temp AS $$
 SELECT coalesce(jsonb_agg(ligne),'[]'::jsonb) FROM (
  SELECT jsonb_build_object('type','vision','utilisateur',utilisateur,'confirmee_a',floor(extract(epoch FROM demande_a))::bigint) ligne,demande_a
   FROM demandes WHERE (archive_confirmee_a IS NULL OR archive_sha256 IS NULL)
  UNION ALL
  SELECT jsonb_build_object('type','fermeture_commune','sujet',sujet,'emetteur',emetteur,'outils',jsonb_build_object('vision',comptes),'confirmee_a',floor(extract(epoch FROM demande_a))::bigint),demande_a
   FROM fermetures WHERE (archive_confirmee_a IS NULL OR archive_sha256 IS NULL)
  ORDER BY demande_a LIMIT 20
 ) p
$$;
ALTER FUNCTION vision_effacements.prochaines_archives() OWNER TO vision_journal_owner;
CREATE FUNCTION vision_effacements.acquitter_archive(t text,u text,date_unix bigint,sha text,c jsonb) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,vision_effacements,pg_temp AS $$
BEGIN
 IF sha IS NULL OR sha !~ '^[a-f0-9]{64}$' OR date_unix IS NULL OR date_unix<=0 THEN RAISE EXCEPTION 'registre_invalide'; END IF;
 IF t='vision' AND c='[]'::jsonb THEN
   UPDATE demandes SET archive_confirmee_a=coalesce(archive_confirmee_a,clock_timestamp()),archive_sha256=sha
    WHERE utilisateur=u AND floor(extract(epoch FROM demande_a))::bigint=date_unix;
 ELSIF t='fermeture_commune' THEN
   UPDATE fermetures SET archive_confirmee_a=coalesce(archive_confirmee_a,clock_timestamp()),archive_sha256=sha
    WHERE sujet=u AND floor(extract(epoch FROM demande_a))::bigint=date_unix AND comptes=c;
 ELSE RAISE EXCEPTION 'registre_invalide'; END IF;
 RETURN FOUND;
END $$;
ALTER FUNCTION vision_effacements.acquitter_archive(text,text,bigint,text,jsonb) OWNER TO vision_journal_owner;
CREATE FUNCTION vision_effacements.etat_rejeu() RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,vision_effacements,pg_temp AS $$
 SELECT jsonb_build_object('revision',(SELECT numero FROM revision WHERE singleton),
   'attente',(SELECT count(*) FROM demandes WHERE (archive_confirmee_a IS NULL OR archive_sha256 IS NULL))+(SELECT count(*) FROM fermetures WHERE (archive_confirmee_a IS NULL OR archive_sha256 IS NULL)))
$$;
ALTER FUNCTION vision_effacements.etat_rejeu() OWNER TO vision_journal_owner;
-- La pagination borne les lignes AVANT leur agrégation.
CREATE FUNCTION vision_effacements.lire_rejeu(apres text) RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,vision_effacements,pg_temp AS $$
 SELECT coalesce(jsonb_agg(ligne ORDER BY cle),'[]'::jsonb) FROM (
  SELECT * FROM (
   SELECT 'v:'||utilisateur cle,jsonb_build_object('cle','v:'||utilisateur,'type','vision','utilisateur',utilisateur) ligne FROM demandes WHERE archive_confirmee_a IS NOT NULL AND archive_sha256 IS NOT NULL
   UNION ALL
   SELECT 'f:'||sujet,jsonb_build_object('cle','f:'||sujet,'type','fermeture_commune','sujet',sujet,'emetteur',emetteur,'outils',jsonb_build_object('vision',comptes)) FROM fermetures WHERE archive_confirmee_a IS NOT NULL AND archive_sha256 IS NOT NULL
  ) p WHERE cle>apres ORDER BY cle LIMIT 100
 ) q
$$;
ALTER FUNCTION vision_effacements.lire_rejeu(text) OWNER TO vision_journal_owner;
-- Le worker normal ne parcourt que les intentions acquittées restant à
-- appliquer. Le délai de fermeture laisse le hook natif terminer sa réponse.
CREATE FUNCTION vision_effacements.prochains_rejeux() RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,vision_effacements,pg_temp AS $$
 SELECT coalesce(jsonb_agg(ligne ORDER BY cle),'[]'::jsonb) FROM (
  SELECT * FROM (
   SELECT 'v:'||utilisateur cle,jsonb_build_object('cle','v:'||utilisateur,'type','vision','utilisateur',utilisateur,'archive_sha256',archive_sha256) ligne
    FROM demandes WHERE archive_confirmee_a IS NOT NULL AND archive_sha256 IS NOT NULL AND applique_sha256 IS DISTINCT FROM archive_sha256
   UNION ALL
   SELECT 'f:'||sujet,jsonb_build_object('cle','f:'||sujet,'type','fermeture_commune','sujet',sujet,'emetteur',emetteur,'outils',jsonb_build_object('vision',comptes),'archive_sha256',archive_sha256)
    FROM fermetures WHERE archive_confirmee_a IS NOT NULL AND archive_sha256 IS NOT NULL AND applique_sha256 IS DISTINCT FROM archive_sha256
     AND demande_a<=clock_timestamp()-interval '120 seconds'
  ) p ORDER BY cle LIMIT 100
 ) q
$$;
ALTER FUNCTION vision_effacements.prochains_rejeux() OWNER TO vision_journal_owner;
CREATE FUNCTION vision_effacements.acquitter_rejeu(cle text,sha text) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,vision_effacements,pg_temp AS $$
BEGIN
 IF sha IS NULL OR sha !~ '^[a-f0-9]{64}$' OR cle IS NULL OR cle !~ '^[vf]:[A-Za-z0-9_.-]{1,64}$' THEN RAISE EXCEPTION 'registre_invalide'; END IF;
 IF left(cle,2)='v:' THEN
  UPDATE demandes SET applique_sha256=sha WHERE utilisateur=substr(cle,3) AND archive_confirmee_a IS NOT NULL AND archive_sha256=sha;
 ELSE
  UPDATE fermetures SET applique_sha256=sha WHERE sujet=substr(cle,3) AND archive_confirmee_a IS NOT NULL AND archive_sha256=sha;
 END IF;
 RETURN FOUND;
END $$;
ALTER FUNCTION vision_effacements.acquitter_rejeu(text,text) OWNER TO vision_journal_owner;
REVOKE ALL ON ALL TABLES IN SCHEMA vision_effacements FROM PUBLIC,vision_journal_writer,vision_journal_import,vision_journal_archiviste,vision_journal_rejeu,vision_journal_fermeture;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA vision_effacements FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION vision_effacements.importer_fermeture(text,bigint) FROM vision_journal_import;
GRANT EXECUTE ON FUNCTION vision_effacements.importer_fermeture(text,bigint,jsonb) TO vision_journal_import;
GRANT USAGE ON SCHEMA vision_effacements TO vision_journal_archiviste,vision_journal_rejeu,vision_journal_fermeture;
GRANT EXECUTE ON FUNCTION vision_effacements.prochaines_archives(),vision_effacements.acquitter_archive(text,text,bigint,text,jsonb) TO vision_journal_archiviste;
GRANT EXECUTE ON FUNCTION vision_effacements.etat_rejeu(),vision_effacements.lire_rejeu(text) TO vision_journal_rejeu;
GRANT EXECUTE ON FUNCTION vision_effacements.prochains_rejeux(),vision_effacements.acquitter_rejeu(text,text) TO vision_journal_rejeu;
GRANT EXECUTE ON FUNCTION vision_effacements.consigner_fermeture(text,text,jsonb) TO vision_journal_fermeture;
COMMIT;
