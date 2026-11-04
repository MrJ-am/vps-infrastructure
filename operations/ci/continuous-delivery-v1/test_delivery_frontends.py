import io,json,tarfile,unittest
import delivery_frontends as D


class Frontends(unittest.TestCase):
    def setUp(self):
        self.bindings={'proposal':'a'*64,'sources':{'platform':'b'*40},
                       'styles':{name:'c'*40 for name in D.NAMES},'toolchains_sha256':'d'*64}

    def archive(self,change=None,extra=()):
        files=[]
        for group in sorted(D.NAMES):
            payload=b'invented frontend'
            metadata={'schema_version':1,'artifact':group+'-elm','deployment_authorized':False,
                      'input_manifest_sha256':self.bindings['proposal'],
                      'runtime_qualification':'local-verifier-content-only',
                      'source_commits':self.bindings['sources'],'style_revision':'c'*40,
                      'toolchains_lock_sha256':'d'*64,'payload_sha256':{'index.html':D.digest(payload)}}
            if change and group=='log':change(metadata)
            files.extend([(group+'/index.html',payload,tarfile.REGTYPE),
                          (group+'/artifact.json',json.dumps(metadata).encode(),tarfile.REGTYPE)])
        stream=io.BytesIO()
        with tarfile.open(fileobj=stream,mode='w:') as archive:
            for name,raw,kind in files+list(extra):
                info=tarfile.TarInfo(name);info.size=len(raw);info.mode=0o444;info.type=kind
                if kind!=tarfile.REGTYPE:info.linkname='../../outside'
                archive.addfile(info,io.BytesIO(raw))
        return stream.getvalue()

    def validate(self,raw):return D.validate(raw,archive_sha256=D.digest(raw),**self.bindings)

    def test_complete_invented_set(self):
        files=self.validate(self.archive())
        self.assertEqual(set(files),D.NAMES)
        self.assertTrue(all(len(items)==2 for items in files.values()))

    def test_hash_is_bound_before_archive_parsing(self):
        with self.assertRaises(ValueError):
            D.validate(self.archive(),archive_sha256='0'*64,**self.bindings)

    def test_reject_paths_duplicates_links_and_special_files(self):
        for name,kind in [('../outside',tarfile.REGTYPE),('/absolute',tarfile.REGTYPE),
                          ('log/../../outside',tarfile.REGTYPE),('log/index.html',tarfile.REGTYPE),
                          ('log/link',tarfile.SYMTYPE),('log/hard',tarfile.LNKTYPE),
                          ('log/fifo',tarfile.FIFOTYPE),('log\\other/file',tarfile.REGTYPE)]:
            with self.subTest(name=name,kind=kind),self.assertRaises(ValueError):
                self.validate(self.archive(extra=[(name,b'',kind)]))

    def test_reject_added_undeclared_payload(self):
        with self.assertRaises(ValueError):self.validate(self.archive(extra=[('log/unlisted.js',b'x',tarfile.REGTYPE)]))

    def test_reject_mismatched_manifest_bindings(self):
        for key,value in [('deployment_authorized',True),('schema_version',True),
                          ('input_manifest_sha256','e'*64),('source_commits',{}),
                          ('style_revision','e'*40),('toolchains_lock_sha256','e'*64),
                          ('payload_sha256',{'index.html':'0'*64})]:
            with self.subTest(key=key),self.assertRaises(ValueError):
                self.validate(self.archive(change=lambda m:m.update({key:value})))

    def test_reject_file_used_as_directory_even_if_declared(self):
        def change(m):m['payload_sha256']['index.html/child']=D.digest(b'x')
        with self.assertRaises(ValueError):
            self.validate(self.archive(change=change,extra=[('log/index.html/child',b'x',tarfile.REGTYPE)]))


if __name__=='__main__':unittest.main()
