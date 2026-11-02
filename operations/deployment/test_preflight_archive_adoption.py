import json
import unittest

import preflight_archive_adoption as p


class ArchiveDiagnosis(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.module=p.load_module()

    def image(self,key=None,message=b'',extra=None,marker=None):
        db=self.module.reference(native=True,hashes=2,marker=marker)
        try:
            if key is not None:
                db.execute('INSERT INTO courriels(cle,message,cree,etat) VALUES(?,?,?,?)',(key,message,1,'attente'))
            if extra:db.executescript(extra)
            db.commit();return db.serialize()
        finally:db.close()

    def test_qualified_reader_merges_two_invented_sources(self):
        inputs={'closure':self.image('closure:invented'), 'global':self.image('global:invented')}
        value,result=p.classify_sources(self.module,inputs)
        self.assertEqual(value['code'],'SOURCE_MERGE_ACCEPTED')
        self.assertEqual(result,self.module.merge(inputs['closure'],inputs['global'],profile='archive'))
        self.assertNotIn('closure:invented',json.dumps(value))

    def test_unknown_global_schema_is_identified_without_export(self):
        value,result=p.classify_sources(self.module,{'closure':self.image(),
            'global':self.image(extra='CREATE TABLE invented_private_contents(value TEXT);')})
        self.assertEqual(value['code'],'GLOBAL_SCHEMA_OR_INTEGRITY_REFUSED')
        self.assertFalse(value['shapes']['global']['object_identities_compatible'])
        self.assertIsNone(result)
        self.assertNotIn('invented_private_contents',json.dumps(value))

    def test_textual_schema_difference_is_not_silently_accepted(self):
        db=self.module.connection()
        try:
            db.executescript(self.module.schema('native-mail.sql').replace('cle TEXT','cle   TEXT'))
            raw=db.serialize()
        finally:db.close()
        value,_=p.classify_sources(self.module,{'closure':self.image(),'global':raw})
        self.assertEqual(value['code'],'GLOBAL_SCHEMA_OR_INTEGRITY_REFUSED')
        shape=value['shapes']['global']
        self.assertTrue(shape['object_identities_compatible'])
        self.assertTrue(shape['mail_column_layout_compatible'])
        self.assertFalse(shape['exact_schema_accepted'])

    def test_different_same_key_refuses_without_key_or_message(self):
        value,result=p.classify_sources(self.module,{'closure':self.image('INVENTED_PRIVATE_KEY',b'PRIVATE_A'),
            'global':self.image('INVENTED_PRIVATE_KEY',b'PRIVATE_B')})
        self.assertEqual(value['code'],'MAIL_KEY_CONFLICT')
        self.assertIsNone(result)
        self.assertNotIn('PRIVATE',json.dumps(value))

    def test_bad_marker_is_distinguished_from_schema(self):
        raw=self.image(marker='closure',extra="INSERT INTO fermetures VALUES('invalid identifier',1,NULL);")
        value,_=p.classify_sources(self.module,{'closure':raw,'global':self.image()})
        self.assertEqual(value['code'],'CLOSURE_MARKER_CONTRACT_REFUSED')

    def test_existing_different_state_never_invokes_publication(self):
        first=self.module.merge(self.image('a'),self.image(),profile='archive')
        second=self.module.merge(self.image('b'),self.image(),profile='archive')
        meta={'directory':{'present':True,'expected_metadata':True},
              'installed':{'present':True,'expected_metadata':True},'pending':{'present':False}}
        value=p.classify_target(self.module,first,meta,lambda _:second)
        self.assertEqual(value['code'],'INSTALLED_TARGET_DIFFERENT')

    def test_empty_target_only_proves_preconditions(self):
        target=self.module.merge(self.image(),self.image(),profile='archive')
        meta={'directory':{'present':True,'expected_metadata':True},
              'installed':{'present':False},'pending':{'present':False}}
        value=p.classify_target(self.module,target,meta,lambda _:self.fail('No file may be read'))
        self.assertEqual(value['code'],'TARGET_PUBLICATION_PRECONDITIONS_ACCEPTED')
        self.assertFalse(value['publication_io_success_proved'])
        self.assertFalse(value['unit_readonly_mount_reobserved'])


if __name__=='__main__':unittest.main()
