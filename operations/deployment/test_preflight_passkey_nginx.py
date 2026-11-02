import unittest
import preflight_passkey_nginx as probe

TLS=b'server { listen 443 ssl; listen [::]:443 ssl; server_name log.mrj.am; location / { return 200 "quoted } ; #"; } }'
HTTP=b'server { listen 80; server_name log.mrj.am; return 301 https://log.mrj.am$request_uri; }'


class ProbeTest(unittest.TestCase):
    def test_precise_byte_position_and_retained_comment(self):
        raw=b'# commentaire \xe9\nhttp { '+HTTP+b'\n'+TLS+b'\n}'
        begin,end=probe.server_position(raw)
        self.assertEqual(raw[begin:end+1],TLS)

    def test_duplicate_or_alias_servers_refused(self):
        for content in (TLS+TLS,TLS.replace(b'log.mrj.am;',b'log.mrj.am alias.invalid;')):
            with self.subTest(content=content),self.assertRaises(ValueError):
                probe.server_position(b'http { '+content+b' }')

    def test_server_includes_and_existing_prefix_refused(self):
        for directive in (b'include /private/anything;',b'location /_mrjam-worker-provision/ { return 200; }'):
            with self.subTest(directive=directive),self.assertRaises(ValueError):
                probe.server_position(b'http { '+TLS[:-1]+directive+b'} }')

    def test_missing_tls_and_mixed_or_other_ports_refused(self):
        for server in (HTTP,TLS.replace(b'listen 443 ssl;',b'listen 80;'),TLS.replace(b'443',b'8443')):
            with self.subTest(server=server),self.assertRaises(ValueError):
                probe.server_position(b'http { '+server+b' }')

    def test_malformed_config_refused(self):
        for raw in (b'http {',b'http { '+TLS,b'http { '+TLS+b'}\0',b'http { '+TLS+b'} trailing'):
            with self.subTest(raw=raw),self.assertRaises(ValueError):probe.server_position(raw)

    def test_exact_exec(self):
        binary='/nix/store/'+'a'*32+'-nginx-1.30.4/bin/nginx'
        raw='{ path='+binary+' ; argv[]='+binary+' -c '+probe.CONFIG+' ; ignore_errors=no ; }'
        self.assertEqual(probe.parse_exec(raw),binary)
        for wrong in (raw+' '+raw,raw.replace(' -c ',' -g arbitrary -c '),raw.replace(probe.CONFIG,'/private/nginx.conf')):
            with self.subTest(raw=wrong),self.assertRaises(ValueError):probe.parse_exec(wrong)


if __name__=='__main__':unittest.main()
