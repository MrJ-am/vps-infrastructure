SELECT pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(pg_catalog.jsonb_build_object(
 'relations',(SELECT pg_catalog.jsonb_agg(pg_catalog.jsonb_build_array(c.relname,c.relkind,c.relpersistence,c.relrowsecurity,c.relforcerowsecurity,c.relreplident,c.reloptions,a.amname) ORDER BY c.relname)
   FROM pg_catalog.pg_class c LEFT JOIN pg_catalog.pg_am a ON a.oid=c.relam WHERE c.relnamespace='audition'::pg_catalog.regnamespace),
 'columns',(SELECT pg_catalog.jsonb_agg(pg_catalog.jsonb_build_array(c.relname,a.attnum,a.attname,pg_catalog.format_type(a.atttypid,a.atttypmod),a.attnotnull,a.attidentity,a.attgenerated,a.attisdropped,co.collname,n.nspname) ORDER BY c.relname,a.attnum)
   FROM pg_catalog.pg_attribute a JOIN pg_catalog.pg_class c ON c.oid=a.attrelid LEFT JOIN pg_catalog.pg_collation co ON co.oid=a.attcollation LEFT JOIN pg_catalog.pg_namespace n ON n.oid=co.collnamespace
   WHERE c.relnamespace='audition'::pg_catalog.regnamespace AND a.attnum>0),
 'defaults',(SELECT pg_catalog.jsonb_agg(pg_catalog.jsonb_build_array(c.relname,d.adnum,pg_catalog.pg_get_expr(d.adbin,d.adrelid)) ORDER BY c.relname,d.adnum)
   FROM pg_catalog.pg_attrdef d JOIN pg_catalog.pg_class c ON c.oid=d.adrelid WHERE c.relnamespace='audition'::pg_catalog.regnamespace),
 'constraints',(SELECT pg_catalog.jsonb_agg(pg_catalog.jsonb_build_array(c.relname,x.conname,x.contype,x.condeferrable,x.condeferred,x.convalidated,pg_catalog.pg_get_constraintdef(x.oid)) ORDER BY c.relname,x.conname)
   FROM pg_catalog.pg_constraint x JOIN pg_catalog.pg_class c ON c.oid=x.conrelid WHERE c.relnamespace='audition'::pg_catalog.regnamespace),
 'indexes',(SELECT pg_catalog.jsonb_agg(pg_catalog.jsonb_build_array(c.relname,i.indisunique,i.indisprimary,i.indisexclusion,i.indisvalid,i.indisready,pg_catalog.pg_get_indexdef(c.oid)) ORDER BY c.relname)
   FROM pg_catalog.pg_index i JOIN pg_catalog.pg_class c ON c.oid=i.indexrelid WHERE c.relnamespace='audition'::pg_catalog.regnamespace),
 'policies',(SELECT pg_catalog.jsonb_agg(pg_catalog.jsonb_build_array(c.relname,p.polname,p.polcmd,p.polpermissive,p.polroles,pg_catalog.pg_get_expr(p.polqual,p.polrelid),pg_catalog.pg_get_expr(p.polwithcheck,p.polrelid)) ORDER BY c.relname,p.polname)
   FROM pg_catalog.pg_policy p JOIN pg_catalog.pg_class c ON c.oid=p.polrelid WHERE c.relnamespace='audition'::pg_catalog.regnamespace),
 'functions',(SELECT pg_catalog.jsonb_agg(pg_catalog.jsonb_build_array(p.proname,pg_catalog.pg_get_function_identity_arguments(p.oid),pg_catalog.pg_get_functiondef(p.oid)) ORDER BY p.proname,pg_catalog.pg_get_function_identity_arguments(p.oid))
   FROM pg_catalog.pg_proc p WHERE p.pronamespace='audition'::pg_catalog.regnamespace),
 'triggers',(SELECT pg_catalog.jsonb_agg(pg_catalog.jsonb_build_array(c.relname,t.tgname,t.tgenabled,pg_catalog.pg_get_triggerdef(t.oid)) ORDER BY c.relname,t.tgname)
   FROM pg_catalog.pg_trigger t JOIN pg_catalog.pg_class c ON c.oid=t.tgrelid WHERE c.relnamespace='audition'::pg_catalog.regnamespace AND NOT t.tgisinternal),
 'sequences',(SELECT pg_catalog.jsonb_agg(pg_catalog.jsonb_build_array(c.relname,pg_catalog.format_type(s.seqtypid,NULL),s.seqstart,s.seqincrement,s.seqmax,s.seqmin,s.seqcache,s.seqcycle) ORDER BY c.relname)
   FROM pg_catalog.pg_sequence s JOIN pg_catalog.pg_class c ON c.oid=s.seqrelid WHERE c.relnamespace='audition'::pg_catalog.regnamespace),
 'types',(SELECT pg_catalog.jsonb_agg(pg_catalog.jsonb_build_array(t.typname,t.typtype,t.typcategory,t.typnotnull,pg_catalog.format_type(NULLIF(t.typbasetype,0),t.typtypmod)) ORDER BY t.typname)
   FROM pg_catalog.pg_type t WHERE t.typnamespace='audition'::pg_catalog.regnamespace)
)::text,'UTF8')),'hex')
