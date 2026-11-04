-- Entirely invented local-only PostgreSQL fixture. Never send to the VPS.
CREATE ROLE vision_identite LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
CREATE SCHEMA vision_gestion;
CREATE TABLE public.synthetic_principals (
 issuer text NOT NULL, subject text NOT NULL, username text NOT NULL,
 active boolean NOT NULL, administrator boolean NOT NULL,
 PRIMARY KEY(issuer,subject));
REVOKE ALL ON public.synthetic_principals FROM PUBLIC;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
CREATE FUNCTION vision_gestion.identifier(emetteur text, sujet text)
RETURNS jsonb LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
 SELECT COALESCE(
   (SELECT jsonb_build_object('actif',active,'utilisateur',username,'administrateur',administrator)
    FROM public.synthetic_principals WHERE issuer=emetteur AND subject=sujet),
   jsonb_build_object('actif',false,'erreur','identite_inconnue'))
$$;
REVOKE ALL ON SCHEMA vision_gestion FROM PUBLIC;
GRANT USAGE ON SCHEMA vision_gestion TO vision_identite;
REVOKE ALL ON FUNCTION vision_gestion.identifier(text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION vision_gestion.identifier(text,text) TO vision_identite;
INSERT INTO public.synthetic_principals VALUES
 ('https://log.mrj.am/oauth2/openid/mrjam-vision','11111111-1111-4111-8111-111111111111','synthetic_alice',true,true),
 ('https://log.mrj.am/oauth2/openid/mrjam-vision','22222222-2222-4222-8222-222222222222','synthetic_bob',true,false);
