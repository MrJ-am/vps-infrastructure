import contextlib
import importlib.util
import io
import ipaddress
import json
from pathlib import Path
import socket
import types
import unittest
from unittest import mock

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location('tcp_probe', HERE / 'classify_tcp_listeners_005.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def table(entries, ipv6=False):
    result = ['sl local_address ' + ('remote_address' if ipv6 else 'rem_address') + ' st']
    for index, (address, port, state) in enumerate(entries):
        data = ipaddress.ip_address(address).packed
        encoded = b''.join(data[i:i+4][::-1] for i in range(0, len(data), 4)).hex().upper()
        result.append(f'{index}: {encoded}:{port:04X} IGNORED_PEER {state} NEVER_EXPORT_IGNORED_FIELDS')
    return ('\n'.join(result) + '\n').encode()


class TestListeners(unittest.TestCase):
    def test_expected_and_llmnr_are_distinct_from_reachability(self):
        raw = table([(address, port, '0A') for address, port in
                     [('0.0.0.0', p) for p in (22, 80, 443, 2222, 5355)]
                     + [('127.0.0.53', 53), ('127.0.0.1', 38101)]])
        value = m.classify(m.parse(raw))
        self.assertEqual(value['unexpected_nonloopback_ports'], [5355])
        self.assertTrue(value['only_unexpected_nonloopback_is_llmnr_port'])
        self.assertTrue(value['private_application_ports_loopback_only'])
        self.assertTrue(all(value['expected_public_ports_present'].values()))
        self.assertNotIn('NEVER_EXPORT', json.dumps(value))
        self.assertNotIn('127.0.0.53', json.dumps(value))

    def test_ipv6_word_order_and_mapped_addresses(self):
        raw = table([('::1', 8443, '0A'), ('::ffff:127.0.0.1', 38102, '0A'),
                     ('::', 5355, '0A'), ('::ffff:192.0.2.1', 3002, '0A'),
                     ('fe80::1234', 9000, '0A'), ('2001:db8::1', 1, '01')], ipv6=True)
        self.assertEqual(m.parse(raw, True), [(8443, 'ipv6', 'loopback'),
                         (38102, 'ipv6', 'mapped_loopback'), (5355, 'ipv6', 'wildcard'),
                         (3002, 'ipv6', 'mapped_nonloopback'), (9000, 'ipv6', 'link_local')])
        self.assertFalse(m.classify(m.parse(raw, True))['private_application_ports_loopback_only'])

    def test_real_kernel_loopback_listeners_ipv4_ipv6(self):
        for family, address, file, ipv6 in ((socket.AF_INET, '127.0.0.1', '/proc/net/tcp', False),
                                          (socket.AF_INET6, '::1', '/proc/net/tcp6', True)):
            with socket.socket(family, socket.SOCK_STREAM) as sock:
                sock.bind((address, 0))
                sock.listen(1)
                self.assertIn((sock.getsockname()[1], 'ipv6' if ipv6 else 'ipv4', 'loopback'),
                              m.parse(Path(file).read_bytes(), ipv6))

    def test_malformed_and_overbound_are_refused(self):
        valid = table([('127.0.0.1', 22, '0A')])
        for raw in (b'', b'x' * (m.MAX_BYTES + 1), valid.replace(b'0100007F', b'010000'),
                    valid.replace(b':0016', b':0000'), valid.replace(b' 0A ', b' XX '),
                    valid.splitlines()[0] + b'\n' + (valid.splitlines()[1] + b'\n') * (m.MAX_ROWS + 1)):
            with self.assertRaises((m.Refused, ValueError, UnicodeError)):
                m.parse(raw)
        with self.assertRaises(m.Refused):
            m.classify([(number, 'ipv4', 'wildcard') for number in range(1, 66)])

    def test_generation_gate_precedes_any_file_read(self):
        with mock.patch.object(m.os.path, 'realpath', return_value='/wrong'), mock.patch.object(m, 'read_fixed') as read:
            with self.assertRaises(m.Refused):
                m.collect()
            read.assert_not_called()

    def test_exception_text_is_never_exported(self):
        output = io.StringIO()
        with mock.patch.object(m.os, 'geteuid', return_value=0), \
             mock.patch.object(m.os, 'uname', return_value=types.SimpleNamespace(nodename='srv1982677')), \
             mock.patch.object(m.sys, 'argv', ['fixed']), \
             mock.patch.object(m.resource, 'setrlimit'), mock.patch.object(m.signal, 'signal'), \
             mock.patch.object(m.signal, 'alarm'), mock.patch.object(m, 'collect', side_effect=ValueError('PRIVATE_EXCEPTION_TEXT')), \
             contextlib.redirect_stdout(output):
            self.assertEqual(m.main(), 1)
        self.assertEqual(json.loads(output.getvalue()), {'schema_version': 1, 'code': 'TCP_LISTENER_CLASSIFICATION_REFUSED'})


if __name__ == '__main__':
    unittest.main()
