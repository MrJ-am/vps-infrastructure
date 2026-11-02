import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import postflight_barriers_v5 as m


class BarrierTests(unittest.TestCase):
    def test_unit_parser_rejects_arbitrary_fields_and_ambiguous_identity(self):
        self.assertEqual(m.parse_units('Id=a.service\nMainPID=0',{'a.service'})['a.service']['MainPID'],'0')
        for raw in ('Id=a.service\nEnvironment=SECRET','Id=a.service\nId=b.service',
                    'Id=a.service\n\nId=a.service','Id=unselected.service'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):m.parse_units(raw,{'a.service'})

    def test_tcp_listener_classification_covers_ipv6_and_mapped_loopback(self):
        prefix=b' header\n 0: '
        suffix=b' 00000000:0000 0A 0 0 0\n'
        self.assertEqual(m.listeners(prefix+b'0100007F:0BBA'+suffix),[(3002,True)])
        self.assertEqual(m.listeners(prefix+b'00000000:0D05'+suffix),[(3333,False)])
        self.assertEqual(m.listeners(prefix+b'00000000000000000000000001000000:20FB'+suffix,True),[(8443,True)])
        self.assertEqual(m.listeners(prefix+b'0000000000000000FFFF00000100007F:20FB'+suffix,True),[(8443,True)])

    def test_live_process_cannot_hide_extra_capability_or_changed_uid(self):
        value=b'Uid:\t944\t944\t944\t944\nGid:\t944\t944\t944\t944\nCapEff:\t0000000000000000\nCapAmb:\t0000000000000000\nNoNewPrivs:\t1\n'
        with patch.object(m,'read_public',return_value=value):
            self.assertTrue(all(m.process_barriers('12',944,944).values()))
        with patch.object(m,'read_public',return_value=value.replace(b'CapEff:\t0000000000000000',b'CapEff:\t0000000000000001')):
            self.assertFalse(m.process_barriers('12',944,944)['no_effective_or_ambient_caps'])
        with patch.object(m,'read_public',return_value=value):
            self.assertFalse(m.process_barriers('12',945,944)['uids_match'])
        self.assertEqual(m.process_barriers('0',944,944),{'running_observed':False})

    def test_identity_broker_account_group_differs_from_service_group(self):
        item={'FragmentPath':str(Path(m.PROMOTED+'/etc/systemd/system/mrjam-identity.service').resolve()),
              'DropInPaths':'','User':'mrjam-metier','Group':'mrjam-log-readers',
              'CapabilityBoundingSet':'','AmbientCapabilities':'','NoNewPrivileges':'yes',
              'ProtectSystem':'strict','ProtectHome':'yes','MainPID':'0'}
        with patch.object(m.pwd,'getpwnam',return_value=SimpleNamespace(pw_uid=984,pw_gid=984)), \
             patch.object(m.os,'getgrouplist',return_value=[984]), \
             patch.object(m.grp,'getgrnam',return_value=SimpleNamespace(gr_gid=1)):
            value=m.worker('mrjam-identity',item)
        self.assertTrue(value['identity_matches'])
        self.assertTrue(value['unit_user_group_match'])
        self.assertEqual(value['process'],{'running_observed':False})

    def test_firewall_rejects_extra_accept_rule_and_missing_terminal_drop(self):
        rules=['-N nixos-fw','-A nixos-fw -i lo -j nixos-fw-accept',
               '-A nixos-fw -m conntrack --ctstate RELATED,ESTABLISHED -j nixos-fw-accept']
        rules += ['-A nixos-fw -p tcp -m tcp --dport '+str(port)+' -j nixos-fw-accept' for port in (22,80,443,2222)]
        rules += ['-A nixos-fw -j nixos-fw-log-refuse']
        values={'INPUT':['-P INPUT ACCEPT','-A INPUT -j nixos-fw'],'nixos-fw':rules,
                'nixos-fw-accept':['-N nixos-fw-accept','-A nixos-fw-accept -j ACCEPT'],
                'nixos-fw-refuse':['-N nixos-fw-refuse','-A nixos-fw-refuse -j DROP'],
                'nixos-fw-log-refuse':['-N nixos-fw-log-refuse','-A nixos-fw-log-refuse -j nixos-fw-refuse']}
        with patch.object(m,'run',side_effect=lambda arguments:'\n'.join(values[arguments[-1]])):
            self.assertTrue(all(m.firewall_family('iptables').values()))
            rules.insert(-1,'-A nixos-fw -p udp --dport 1234 -j nixos-fw-accept')
            self.assertFalse(m.firewall_family('iptables')['no_unrecognized_input_exception'])
            values['nixos-fw-refuse'][-1]='-A nixos-fw-refuse -j ACCEPT'
            self.assertFalse(m.firewall_family('iptables')['terminal_drop_present'])

    def test_native_sshd_configuration_output_is_closed_and_key_only(self):
        if not Path(m.SSHD).exists():self.skipTest('Pinned OpenSSH not available')
        config=Path(m.PROMOTED+'/etc/ssh/sshd_config').resolve()
        result=subprocess.run([m.SSHD,'-G','-f',str(config)],capture_output=True,check=True)
        values={line.split(' ',1)[0].lower():line.split(' ',1)[1] for line in result.stdout.decode().splitlines() if ' ' in line}
        self.assertEqual(values['passwordauthentication'],'no')
        self.assertEqual(values['kbdinteractiveauthentication'],'no')
        self.assertIn(values['permitrootlogin'],('without-password','prohibit-password'))
        self.assertEqual(values['port'],'22')

    def test_command_output_is_bounded(self):
        with self.assertRaises(ValueError):
            m.run([sys.executable,'-c',"print('X'*300000)"])

    def test_openssh_path_is_not_an_override_option(self):
        config=Path(m.PROMOTED+'/etc/ssh/sshd_config').resolve()
        fragment=str(Path(m.PROMOTED+'/etc/systemd/system/sshd.service').resolve())
        native=subprocess.run([m.SSHD,'-G','-f',str(config)],capture_output=True,check=True).stdout.decode()
        title=('sshd: '+m.SSHD+' -D -f /etc/ssh/sshd_config [listener]').encode()
        resolve=Path.resolve
        read_public=m.read_public
        item={'MainPID':'123','ActiveState':'active','FragmentPath':fragment,'DropInPaths':''}
        def resolve_fixed(path,*args,**kwargs):
            return config if str(path)=='/etc/ssh/sshd_config' else resolve(path,*args,**kwargs)
        for command,expected in ((title,True),(title+b' -oPermitRootLogin=yes',False),(title+b' -o PermitRootLogin=yes',False)):
            with self.subTest(expected=expected),patch.object(m.Path,'resolve',resolve_fixed), \
                 patch.object(m,'read_public',side_effect=lambda path,*args:command if str(path)=='/proc/123/cmdline' else read_public(path,*args)), \
                 patch.object(m,'run',return_value=native):
                self.assertIs(m.ssh(item)['running_expected_configuration'],expected)

    def test_failure_never_exports_exception_or_partial_secret(self):
        output=io.StringIO()
        with patch.object(m.os,'geteuid',return_value=0),patch.object(sys,'argv',['probe']), \
             patch.object(m,'collect',side_effect=RuntimeError('INVENTED_SECRET_MUST_NOT_LEAK')), \
             contextlib.redirect_stdout(output):
            self.assertEqual(m.main(),1)
        self.assertEqual(json.loads(output.getvalue()),{'schema_version':1,'code':'BARRIERS_UNAVAILABLE'})


class FragmentMeasurementTests(unittest.TestCase):
    def test_real_promoted_symlink_resolves_to_exact_store_unit(self):
        expected=Path(m.PROMOTED+'/etc/systemd/system/mrjam-rust-blue.service').resolve(strict=True)
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp)/'etc/systemd/system';directory.mkdir(parents=True)
            link=directory/'mrjam-rust-blue.service';link.symlink_to(expected)
            with patch.object(m,'PROMOTED',tmp):
                self.assertNotEqual(str(link),str(expected)) # v4 falsely refused this spelling.
                self.assertTrue(m.fragment_matches_promoted('mrjam-rust-blue',{'FragmentPath':str(link)}))

    def test_fixed_manager_alias_resolves_and_old_or_private_targets_refused(self):
        name='mrjam-rust-blue';expected=Path(m.PROMOTED+'/etc/systemd/system/'+name+'.service').resolve(strict=True)
        alias='/etc/systemd/system/'+name+'.service';original=Path.resolve
        wrong=Path('/nix/store/p6fzklfcay69gl3b69n5zb5l79wx73cr-unit-mrjam-rust-blue.service/mrjam-rust-blue.service')
        def resolution(path,*args,**kwargs):
            if str(path)==alias:return expected
            return original(path,*args,**kwargs)
        with patch.object(Path,'resolve',resolution):
            self.assertTrue(m.fragment_matches_promoted(name,{'FragmentPath':alias}))
        self.assertFalse(m.fragment_matches_promoted(name,{'FragmentPath':str(wrong)}))
        calls=[]
        def no_private(path,*args,**kwargs):
            calls.append(str(path));self.assertNotIn('/var/lib/',str(path));return original(path,*args,**kwargs)
        with patch.object(Path,'resolve',no_private):
            self.assertFalse(m.fragment_matches_promoted(name,{'FragmentPath':'/var/lib/kanidm/private'}))
            self.assertFalse(m.fragment_matches_promoted(name,{'FragmentPath':'/etc/systemd/system/../private'}))
        self.assertEqual(len(calls),2)

    def observe_worker(self,name,item):
        uid,gid=m.WORKERS[name]
        with patch.object(m.pwd,'getpwnam',return_value=SimpleNamespace(pw_uid=uid,pw_gid=gid)), \
             patch.object(m.os,'getgrouplist',return_value=[gid]), \
             patch.object(m.grp,'getgrnam',return_value=SimpleNamespace(gr_gid=1)):
            return m.worker(name,item)

    def test_masked_green_has_no_live_unit_measurement_but_exact_declaration(self):
        item={'LoadState':'masked','ActiveState':'inactive','MainPID':'0','FragmentPath':'/dev/null','DropInPaths':''}
        value=self.observe_worker('mrjam-rust-green',item)
        self.assertTrue(value['inactive_slot_expected']);self.assertTrue(value['qualified_declaration_matches'])
        self.assertEqual(value['process'],{'running_observed':False})
        for field in ('fragment_matches_promoted','unit_user_group_match','unit_no_capabilities','unit_no_new_privileges','unit_protected_filesystem'):
            self.assertIsNone(value[field])
        item['MainPID']='1'
        with patch.object(m,'process_barriers',return_value={'running_observed':True}):
            self.assertFalse(self.observe_worker('mrjam-rust-green',item)['inactive_slot_expected'])

    def test_loaded_inactive_green_does_not_hide_real_hardening_failure(self):
        item={'LoadState':'loaded','ActiveState':'inactive','MainPID':'0','FragmentPath':str(Path(m.PROMOTED+'/etc/systemd/system/mrjam-rust-green.service').resolve()),'DropInPaths':'','User':'root','Group':'root','NoNewPrivileges':'no','ProtectSystem':'no','ProtectHome':'no','AmbientCapabilities':'CAP_SYS_ADMIN','CapabilityBoundingSet':'CAP_SYS_ADMIN'}
        value=self.observe_worker('mrjam-rust-green',item)
        self.assertTrue(value['fragment_matches_promoted']);self.assertTrue(value['qualified_declaration_matches'])
        for field in ('inactive_slot_expected','unit_user_group_match','unit_no_capabilities','unit_no_new_privileges','unit_protected_filesystem'):
            self.assertIs(value[field],False)

    def test_replay_credential_measurement_uses_resolved_fragment_and_keeps_drift(self):
        name='mrjam-vision-replay';expected=Path(m.PROMOTED+'/etc/systemd/system/'+name+'.service').resolve(strict=True)
        alias='/etc/systemd/system/'+name+'.service';original=Path.resolve
        def resolution(path,*args,**kwargs):return expected if str(path)==alias else original(path,*args,**kwargs)
        item={'LoadState':'loaded','ActiveState':'inactive','MainPID':'0','FragmentPath':alias,'DropInPaths':''}
        with patch.object(Path,'resolve',resolution):
            value=self.observe_worker(name,item)
            self.assertTrue(value['fragment_matches_promoted']);self.assertTrue(value['replay_declaration_has_no_provider_token'])
            item['DropInPaths']='/run/systemd/system/foreign.conf'
            self.assertFalse(self.observe_worker(name,item)['replay_declaration_has_no_provider_token'])

    def test_declaration_tamper_remains_visible(self):
        item={'LoadState':'masked','ActiveState':'inactive','MainPID':'0','FragmentPath':'/dev/null','DropInPaths':''}
        with patch.dict(m.QUALIFIED_WORKER_UNITS_SHA256,{'mrjam-rust-green':'0'*64}):
            self.assertFalse(self.observe_worker('mrjam-rust-green',item)['qualified_declaration_matches'])


if __name__=='__main__':unittest.main()
