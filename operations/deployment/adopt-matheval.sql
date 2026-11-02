-- Explicit, one-time adoption after the paired offline snapshot.
-- No collection, administrator or session row is selected, inserted or removed.
BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='30s';
DO $guard$
BEGIN
 IF current_database()<>'matheval'
   OR EXISTS(SELECT FROM pg_roles WHERE rolname IN ('mrjam_matheval_owner','matheval_admin'))
   OR NOT EXISTS(SELECT FROM pg_roles WHERE rolname='matheval_app'
       AND NOT(rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls))
   OR EXISTS(SELECT FROM pg_auth_members WHERE member=(SELECT oid FROM pg_roles WHERE rolname='matheval_app'))
   OR (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
       WHERE n.nspname='public' AND c.relname IN ('corpus','participations','answers','interaction_events','administrators','administrator_sessions')
       AND c.relkind='r')<>6
   OR NOT EXISTS(SELECT FROM pg_attribute WHERE attrelid=to_regclass('public.administrator_sessions')
       AND attname='last_seen' AND atttypid='timestamptz'::regtype AND attnotnull AND NOT attisdropped)
 THEN RAISE EXCEPTION 'MATHEVAL_ADOPTION_PRECONDITION_REFUSED'; END IF;
END $guard$;
CREATE ROLE mrjam_matheval_owner NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT;
CREATE ROLE matheval_admin LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT PASSWORD NULL;
ALTER DATABASE matheval OWNER TO mrjam_matheval_owner;
ALTER SCHEMA public OWNER TO mrjam_matheval_owner;
ALTER TABLE public.corpus OWNER TO mrjam_matheval_owner;
ALTER TABLE public.participations OWNER TO mrjam_matheval_owner;
ALTER TABLE public.answers OWNER TO mrjam_matheval_owner;
ALTER TABLE public.interaction_events OWNER TO mrjam_matheval_owner;
ALTER TABLE public.administrators OWNER TO mrjam_matheval_owner;
ALTER TABLE public.administrator_sessions OWNER TO mrjam_matheval_owner;
REVOKE ALL ON DATABASE matheval FROM PUBLIC,matheval_app,matheval_admin;
GRANT CONNECT ON DATABASE matheval TO matheval_app,matheval_admin;
REVOKE ALL ON SCHEMA public FROM PUBLIC,matheval_app,matheval_admin;
GRANT USAGE ON SCHEMA public TO matheval_app,matheval_admin;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC,matheval_app,matheval_admin;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM PUBLIC,matheval_app,matheval_admin;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC,matheval_app,matheval_admin;
-- Column-level historical grants must not survive a table-level REVOKE.
REVOKE ALL(version,digest,bank,codebook,imported_at) ON public.corpus FROM PUBLIC,matheval_app,matheval_admin;
REVOKE ALL(id,token_hash,bank_version,levels,seed,question_order,production_order,started_at,updated_at,completed_at,revision,payload_hash,snapshot)
 ON public.participations FROM PUBLIC,matheval_app,matheval_admin;
REVOKE ALL(participation_id,question_id,production_id,note,initial_note,x,y,z,evaluated_axes)
 ON public.answers FROM PUBLIC,matheval_app,matheval_admin;
REVOKE ALL(participation_id,sequence,event,occurred_at,elapsed_ms,payload)
 ON public.interaction_events FROM PUBLIC,matheval_app,matheval_admin;
REVOKE ALL(id,username,password_hash,created_at) ON public.administrators FROM PUBLIC,matheval_app,matheval_admin;
REVOKE ALL(token_hash,administrator_id,expires_at,last_seen) ON public.administrator_sessions FROM PUBLIC,matheval_app,matheval_admin;
GRANT SELECT ON public.corpus TO matheval_app;
GRANT SELECT,INSERT,UPDATE ON public.participations TO matheval_app;
GRANT SELECT,INSERT,DELETE ON public.answers TO matheval_app;
GRANT SELECT,INSERT ON public.interaction_events TO matheval_app;
GRANT SELECT ON public.corpus,public.participations,public.answers,public.interaction_events,
 public.administrators,public.administrator_sessions TO matheval_admin;
GRANT INSERT,UPDATE(id) ON public.administrators TO matheval_admin;
GRANT INSERT,UPDATE,DELETE ON public.administrator_sessions TO matheval_admin;
GRANT USAGE ON SEQUENCE public.administrators_id_seq TO matheval_admin;
COMMIT;
