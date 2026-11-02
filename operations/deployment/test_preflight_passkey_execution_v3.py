"""Independent closed-output checks with invented systemd/journal responses."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('probe',Path(__file__).with_name('preflight_passkey_execution_v3.py'))
P=importlib.util.module_from_spec(spec);spec.loader.exec_module(P)


class ClosedProbeTests(unittest.TestCase):
    def run_probe(self,messages,*,bad_state=False):
        calls=[]
        def command(args,limit):
            calls.append((args,limit))
            if args[0].endswith('/systemctl'):
                self.assertEqual(args[-1],P.UNITS[len(calls)-1])
                values={'LoadState':'loaded','ActiveState':'inactive','SubState':'dead','Result':'success',
                        'ExecMainCode':'1','ExecMainStatus':'0','ExecMainStartTimestampMonotonic':'10','ExecMainExitTimestampMonotonic':'11'}
                if bad_state:values['Result']='INVENTED_PRIVATE_VALUE'
                return ''.join(key+'='+values[key]+'\n' for key in P.PROPERTIES)
            self.assertEqual(args,[P.PREVIOUS+'/sw/bin/journalctl','--unit='+P.UNITS[0],'--since=-20min','--no-pager','--output=json','--lines=64'])
            return ''.join(json.dumps({'MESSAGE':message,'PRIVATE_OTHER_FIELD':'INVENTED_PRIVATE_VALUE'})+'\n' for message in messages)
        lock=SimpleNamespace(lstat=lambda:SimpleNamespace(st_mode=0o100600,st_uid=0,st_gid=0,st_nlink=1))
        output=io.StringIO()
        with patch.object(P,'command',command),patch.object(P,'LOCK',lock),patch.object(P.sys,'argv',['probe']), \
             patch.object(P.os,'geteuid',return_value=0),patch.object(P.os.path,'realpath',return_value=P.PREVIOUS),contextlib.redirect_stdout(output):
            P.main()
        self.assertEqual(len(calls),5)
        self.assertNotIn('INVENTED_PRIVATE_VALUE',output.getvalue())
        result=json.loads(output.getvalue())
        self.assertFalse(result['human_cache_read']);self.assertFalse(result['journal_messages_exported']);self.assertFalse(result['worker_lock_contents_read'])
        return result

    def test_exact_stage_count_and_unknown_messages_never_exported(self):
        exact=json.dumps({'error':'KANIDM_WORKER_PROVISION_REFUSED','stage':'ACCESS_RIGHTS'},sort_keys=True,separators=(',',':'))
        result=self.run_probe([exact,exact+' INVENTED_PRIVATE_VALUE',{'unexpected':'INVENTED_PRIVATE_VALUE'},
            'INVENTED_PRIVATE_VALUE',json.dumps({'error':'KANIDM_WORKER_PROVISION_REFUSED','stage':'INVENTED_PRIVATE_VALUE'}),
            json.dumps({'error':'KANIDM_WORKER_PROVISION_SESSION_CLEANUP_REQUIRED','stage':'CLEANUP'},sort_keys=True,separators=(',',':'))])
        self.assertEqual(result['closed_codes_last_20_minutes']['KANIDM_WORKER_PROVISION_REFUSED'],1)
        self.assertEqual(result['closed_stages_last_20_minutes']['ACCESS_RIGHTS'],1)
        self.assertEqual(result['closed_stages_last_20_minutes']['CLEANUP'],1)
        self.assertFalse(result['provision_success_observed'])

    def test_exact_success_and_legacy_error_remain_recognized(self):
        result=self.run_probe([json.dumps(P.SUCCESS,sort_keys=True,separators=(',',':')),
                              '{"error":"KANIDM_WORKER_PROVISION_REFUSED"}'])
        self.assertTrue(result['provision_success_observed'])
        self.assertEqual(result['closed_codes_last_20_minutes']['KANIDM_WORKER_PROVISION_REFUSED'],1)
        self.assertEqual(sum(result['closed_stages_last_20_minutes'].values()),0)

    def test_unrecognized_systemd_value_aborts_without_export(self):
        with self.assertRaises(RuntimeError):self.run_probe([],bad_state=True)


if __name__=='__main__':unittest.main()
