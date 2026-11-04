import unittest
import transaction as T


class PowerLoss(BaseException):
    pass


class Adapter:
    def __init__(self, active=True, fail=None, crash=None):
        self.running = active
        self.journal = None
        self.events = []
        self.fail, self.crash = fail, crash
        self.published = False

    def event(self, name):
        self.events.append(name)
        if self.fail == name:
            raise RuntimeError('SYNTHETIC_FAILURE')
        if self.crash == name:
            raise PowerLoss()

    def read(self):
        return None if self.journal is None else dict(self.journal)

    def save(self, value):
        self.journal = dict(value)
        self.event('save:' + value['phase'])

    def preflight(self): self.event('preflight')
    def active(self): return self.running
    def identifier(self): return 'a' * 32

    def stop(self):
        self.running = False
        self.event('stop')

    def start(self):
        self.running = True
        self.event('start')

    def ready(self):
        assert self.running
        self.event('ready')

    def offline(self):
        assert not self.running
        self.event('offline')

    def capture(self, identifier):
        assert not self.running
        self.event('capture')

    def verify(self, identifier):
        assert not self.running
        self.event('verify')

    def publish(self, identifier):
        assert not self.running
        self.published = True
        self.event('publish')


class Transaction(unittest.TestCase):
    def test_success_captures_offline_and_restores_availability(self):
        a = Adapter()
        self.assertEqual(T.capture(a), 'VISE_BACKUP_COMPLETE')
        self.assertTrue(a.running and a.published)
        self.assertEqual(a.journal['phase'], 'complete')
        self.assertLess(a.events.index('verify'), a.events.index('publish'))
        self.assertLess(a.events.index('publish'), a.events.index('start'))

    def test_originally_stopped_is_not_started(self):
        a = Adapter(active=False)
        T.capture(a)
        self.assertFalse(a.running)
        self.assertNotIn('start', a.events)

    def test_capture_failures_restore_service_without_publication(self):
        for point in ['stop', 'offline', 'capture', 'verify']:
            with self.subTest(point=point):
                a = Adapter(fail=point)
                with self.assertRaises(RuntimeError): T.capture(a)
                self.assertTrue(a.running)
                self.assertFalse(a.published)
                self.assertEqual(a.journal['phase'], 'aborted')

    def test_every_durable_interruption_restores_service(self):
        for point in ['save:quiescing', 'stop', 'offline', 'save:offline',
                      'capture', 'verify', 'save:captured', 'publish',
                      'save:published', 'start', 'ready', 'save:complete']:
            with self.subTest(point=point):
                a = Adapter(crash=point)
                with self.assertRaises(PowerLoss): T.capture(a)
                a.crash = None
                captures = a.events.count('capture')
                T.recover(a)
                self.assertTrue(a.running)
                self.assertIn(a.journal['phase'], {'complete', 'aborted'})
                self.assertEqual(a.events.count('capture'), captures)

    def test_failed_restart_retains_recoverable_intent(self):
        a = Adapter(fail='ready')
        with self.assertRaises(RuntimeError): T.capture(a)
        self.assertEqual(a.journal['phase'], 'published')
        a.fail = None
        T.recover(a)
        self.assertEqual(a.journal['phase'], 'complete')

    def test_pending_journal_recovers_without_starting_new_capture(self):
        a = Adapter(crash='capture')
        with self.assertRaises(PowerLoss): T.capture(a)
        a.crash = None
        T.capture(a)
        self.assertEqual(a.events.count('capture'), 1)
        self.assertEqual(a.journal['phase'], 'aborted')

    def test_invalid_journal_cannot_act(self):
        for bad in [False, {}, {'schema_version': True, 'phase': 'offline',
                                'restart_required': True, 'capture_id': 'a' * 32}]:
            a = Adapter()
            a.journal = bad
            # Bypass the fake adapter's copy: the production parser may yield
            # any JSON type, and the transaction must reject it without action.
            a.read = lambda: bad
            with self.assertRaises(RuntimeError): T.capture(a)
            self.assertEqual(a.events, [])


if __name__ == '__main__':
    unittest.main()
