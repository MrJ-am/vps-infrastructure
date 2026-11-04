"""Synthetic native-SQLite compatibility and proof preservation, no legacy runtime."""
import hashlib
import unittest

import adopt
from test_adopt import IDENTIFIER, OTHER, MESSAGE, requests, mail

URL = 'https://log.mrj.am/ui/reset?token=invented%2Bsecret+value'
BUSINESS_PROOF = hashlib.sha256(b'invented-Lisp-array-proof').hexdigest()


def native_requests(native=True, enrolment=URL):
    source = requests()
    try:
        names, values = adopt.rows(source, 'demandes')
        db = adopt.reference(native=native, with_enrolment=True)
        db.executemany('INSERT INTO demandes VALUES(' + ','.join('?' for _ in range(25)) + ')',
                       [row + (enrolment,) for row in values])
        db.commit()
        return db
    finally:
        source.close()


def native_mail(native=True, semantic=BUSINESS_PROOF, state='attente'):
    source = mail()
    try:
        _, values = adopt.rows(source, 'courriels')
        db = adopt.reference(mail=True, native=native, with_hash=True, with_business_hash=True)
        db.executemany('INSERT INTO courriels VALUES(?,?,?,?,?,?,?,?,?,?)',
                       [(f'enrol:{IDENTIFIER}',) + row[1:] + (semantic,) for row in values])
        db.execute('UPDATE courriels SET etat=?', (state,))
        db.commit()
        return db
    finally:
        source.close()


class NativeAdoption(unittest.TestCase):
    def test_native_and_python_ddl_each_preserve_native_enrolment_and_opaque_mail(self):
        for request_native in (False, True):
            for mail_native in (False, True):
                with self.subTest(request_native=request_native, mail_native=mail_native):
                    request = native_requests(request_native)
                    queue = native_mail(mail_native)
                    before_request, before_queue = request.serialize(), queue.serialize()
                    result = adopt.inspect(adopt.merge(before_request, before_queue), target=True)
                    try:
                        self.assertEqual(result.execute('SELECT enrolement FROM demandes').fetchone(), (URL,))
                        self.assertEqual(adopt.rows(result, 'demandes'), adopt.rows(request, 'demandes'))
                        self.assertEqual(result.execute('SELECT cle,message,empreinte,contenu_sha256,empreinte_metier FROM courriels').fetchone(),
                                         (f'enrol:{IDENTIFIER}', MESSAGE, hashlib.sha256(MESSAGE).hexdigest(), None, BUSINESS_PROOF))
                        self.assertEqual(result.execute('SELECT etat,essais,prochain,accepte,erreur FROM courriels').fetchone(),
                                         queue.execute('SELECT etat,essais,prochain,accepte,erreur FROM courriels').fetchone())
                        self.assertEqual(request.serialize(), before_request)
                        self.assertEqual(queue.serialize(), before_queue)
                    finally:
                        result.close(); request.close(); queue.close()

    def test_native_base_without_enrolment_is_an_explicit_null(self):
        request = adopt.reference(native=True)
        old = requests()
        queue = native_mail()
        try:
            _, values = adopt.rows(old, 'demandes')
            request.executemany('INSERT INTO demandes VALUES(' + ','.join('?' for _ in range(24)) + ')', values)
            request.commit()
            result = adopt.inspect(adopt.merge(request.serialize(), queue.serialize()), target=True)
            try:
                self.assertEqual(result.execute('SELECT enrolement FROM demandes').fetchone(), (None,))
            finally:
                result.close()
        finally:
            request.close(); old.close(); queue.close()

    def test_retained_empty_native_mail_keeps_both_original_proofs(self):
        request, queue = native_requests(enrolment=None), native_mail(state='accepte_relais')
        try:
            queue.execute("UPDATE courriels SET message=X'',accepte=400")
            queue.commit()
            result = adopt.inspect(adopt.merge(request.serialize(), queue.serialize()), target=True)
            try:
                self.assertEqual(result.execute('SELECT message,empreinte,contenu_sha256,empreinte_metier,accepte FROM courriels').fetchone(),
                                 (b'', hashlib.sha256(MESSAGE).hexdigest(), None, BUSINESS_PROOF, 400))
            finally:
                result.close()
        finally:
            request.close(); queue.close()

    def test_url_validation_does_not_normalize_or_fetch(self):
        self.assertTrue(adopt.enrolment_url(URL))
        self.assertTrue(adopt.enrolment_url('https://log.mrj.am/ui/reset?token=synthetic%2bvalue'))
        for value in ('', 'https://evil.invalid/ui/reset?token=invented',
                      'http://log.mrj.am/ui/reset?token=invented',
                      'https://log.mrj.am:8443/ui/reset?token=invented',
                      'https://log.mrj.am/ui/reset?token=', URL + '&extra=x', URL + '#x',
                      'https://log.mrj.am/ui/reset?token=%00',
                      'https://log.mrj.am/ui/reset?token=%ff',
                      'https://log.mrj.am/ui/reset?token=%',
                      'https://log.mrj.am/ui/reset?token=' + 'x'*2049):
            with self.subTest(case=len(value)):
                self.assertFalse(adopt.enrolment_url(value))
                request, queue = native_requests(enrolment=value), native_mail()
                try:
                    with self.assertRaises(adopt.Refused):
                        adopt.merge(request.serialize(), queue.serialize())
                finally:
                    request.close(); queue.close()

    def test_business_proof_is_never_converted_or_invented(self):
        for proof in (None, BUSINESS_PROOF):
            request, queue = native_requests(), native_mail(semantic=proof)
            try:
                result = adopt.inspect(adopt.merge(request.serialize(), queue.serialize()), target=True)
                try:
                    self.assertEqual(result.execute('SELECT contenu_sha256,empreinte_metier FROM courriels').fetchone(), (None, proof))
                finally:
                    result.close()
            finally:
                request.close(); queue.close()
        request, queue = native_requests(), native_mail(semantic='malformed-proof')
        try:
            with self.assertRaises(adopt.Refused):
                adopt.merge(request.serialize(), queue.serialize())
        finally:
            request.close(); queue.close()

    def test_extra_native_objects_and_active_orphan_enrolment_fail_closed(self):
        for sql in ('CREATE TABLE extra(secret TEXT)',
                    'CREATE INDEX native_injected ON demandes(enrolement)',
                    'CREATE VIEW native_injected AS SELECT enrolement FROM demandes',
                    'CREATE TRIGGER native_injected AFTER INSERT ON demandes BEGIN DELETE FROM demandes; END'):
            request, queue = native_requests(), native_mail()
            try:
                request.execute(sql); request.commit()
                with self.assertRaises(adopt.Refused):
                    adopt.merge(request.serialize(), queue.serialize())
            finally:
                request.close(); queue.close()
        request, queue = native_requests(), native_mail()
        try:
            queue.execute('UPDATE courriels SET cle=?', (f'enrol:{OTHER}',)); queue.commit()
            with self.assertRaises(adopt.Refused):
                adopt.merge(request.serialize(), queue.serialize())
        finally:
            request.close(); queue.close()


if __name__ == '__main__':
    unittest.main()
