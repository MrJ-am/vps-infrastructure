import hashlib,io,tarfile,unittest
import package_content as P

def archive(rows):
    output=io.BytesIO()
    with tarfile.open(fileobj=output,mode='w',format=tarfile.USTAR_FORMAT) as stream:
        for name,data,kind in rows:
            entry=tarfile.TarInfo(name);entry.mode=0o444;entry.size=len(data);entry.type=kind
            if kind==tarfile.SYMTYPE:entry.linkname='/tmp/target'
            stream.addfile(entry,io.BytesIO(data))
    return output.getvalue()

class Content(unittest.TestCase):
    def check(self,rows):
        raw=archive(rows);return P.frontend(raw,hashlib.sha256(raw).hexdigest())
    def test_bytes_preserved(self):
        self.assertEqual(self.check([('assets/app.js',b'js',tarfile.REGTYPE),('index.html',b'html',tarfile.REGTYPE)]),
            {'assets/app.js':b'js','index.html':b'html'})
    def test_changed_digest_refused(self):
        raw=archive([('index.html',b'html',tarfile.REGTYPE)])
        with self.assertRaises(ValueError):P.frontend(raw,'0'*64)
    def test_links_traversal_duplicate_and_parent_collision_refused(self):
        for rows in [[('../escape',b'x',tarfile.REGTYPE)], [('/escape',b'x',tarfile.REGTYPE)],
            [('alias',b'',tarfile.SYMTYPE)], [('index.html',b'a',tarfile.REGTYPE)]*2,
            [('index.html',b'a',tarfile.REGTYPE),('index.html/child',b'b',tarfile.REGTYPE)]]:
            with self.subTest(rows=rows),self.assertRaises(ValueError):self.check(rows)
    def test_trailing_content_refused_even_with_matching_digest(self):
        raw=archive([('index.html',b'html',tarfile.REGTYPE)])+b'hidden'
        with self.assertRaises(ValueError):P.frontend(raw,hashlib.sha256(raw).hexdigest())
    def test_entry_page_required(self):
        with self.assertRaises(ValueError):self.check([('other',b'x',tarfile.REGTYPE)])

if __name__=='__main__':unittest.main()
