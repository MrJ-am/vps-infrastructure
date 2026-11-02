import unittest

import adopt


class DDLCompatibility(unittest.TestCase):
    def image(self,mail=None,marker=None):
        db=adopt.connection()
        try:
            db.executescript(mail or adopt.schema('native-mail.sql'))
            if marker:db.executescript(marker)
            db.execute("INSERT INTO courriels(cle,message,cree,etat) VALUES('invented',X'00FF',1,'attente')")
            if marker:db.execute("INSERT INTO fermetures VALUES('invented-subject',2,3)")
            db.commit();return db.serialize()
        finally:db.close()

    def test_closure_whitespace_only_preserves_messages_and_markers(self):
        schema=adopt.schema('closure-markers.sql')
        expected=self.image(marker=schema)
        for changed in (schema.replace('fermetures(', 'fermetures (').replace(',', ', '),
                        schema.replace('(', '(\n\t').replace(',', ',\n\t'),
                        schema.replace('sujet TEXT','sujet\tTEXT').replace('terminee INTEGER','terminee\nINTEGER')):
            with self.subTest(schema=changed):
                observed=self.image(marker=changed)
                empty=adopt.reference(native=True)
                try:
                    a=adopt.merge(expected,empty.serialize(),profile='archive')
                    b=adopt.merge(observed,empty.serialize(),profile='archive')
                    self.assertEqual(a,b)
                finally:empty.close()

    def test_check_constraint_is_rejected_despite_identical_column_pragma(self):
        original=adopt.schema('closure-markers.sql')
        changed=original.replace('sujet TEXT PRIMARY KEY',"sujet TEXT PRIMARY KEY CHECK(sujet != 'invented-forbidden')")
        raw=self.image(marker=changed)
        left=adopt.connection(raw);right=adopt.reference(native=True,marker='closure')
        try:self.assertEqual(left.execute('PRAGMA table_info(fermetures)').fetchall(),right.execute('PRAGMA table_info(fermetures)').fetchall())
        finally:left.close();right.close()
        with self.assertRaises(adopt.Refused):adopt.inspect(raw,scope='closure')

    def test_collation_and_default_changes_remain_refused(self):
        schema=adopt.schema('closure-markers.sql')
        for changed in (schema.replace('TEXT PRIMARY KEY','TEXT COLLATE NOCASE PRIMARY KEY'),
                        schema.replace('terminee INTEGER','terminee INTEGER DEFAULT 0')):
            with self.subTest(schema=changed),self.assertRaises(adopt.Refused):
                adopt.inspect(self.image(marker=changed),scope='closure')

    def test_quoted_literal_whitespace_is_significant(self):
        changed=adopt.schema('native-mail.sql').replace("DEFAULT 'attente'","DEFAULT 'attente '")
        with self.assertRaises(adopt.Refused):adopt.inspect(self.image(mail=changed),scope='global')
        self.assertNotEqual(adopt.ddl_tokens("DEFAULT 'a b'"),adopt.ddl_tokens("DEFAULT 'ab'"))
        self.assertNotEqual(adopt.ddl_tokens('"a b" TEXT'),adopt.ddl_tokens('"ab" TEXT'))

    def test_word_case_comments_and_token_boundaries_are_preserved(self):
        self.assertNotEqual(adopt.ddl_tokens('NOT NULL'),adopt.ddl_tokens('NOTNULL'))
        self.assertNotEqual(adopt.ddl_tokens('INTEGER'),adopt.ddl_tokens('integer'))
        self.assertNotEqual(adopt.ddl_tokens('INTEGER /*extra*/'),adopt.ddl_tokens('INTEGER'))
        self.assertNotEqual(adopt.ddl_tokens('DEFAULT 0'),adopt.ddl_tokens('DEFAULT 00'))
        self.assertNotEqual(adopt.ddl_tokens('DEFAULT -1'),adopt.ddl_tokens('DEFAULT +1'))
        self.assertEqual(adopt.ddl_tokens('INTEGER\n,\tTEXT'),adopt.ddl_tokens('INTEGER,TEXT'))

    def test_unknown_syntax_and_unclosed_quotes_refuse(self):
        for sql in ("TEXT DEFAULT 'unclosed",'TEXT @unknown','TEXT\u00a0NOT NULL','x'*8193):
            with self.subTest(sql=sql[:20]),self.assertRaises(adopt.Refused):adopt.ddl_tokens(sql)


if __name__=='__main__':unittest.main()
