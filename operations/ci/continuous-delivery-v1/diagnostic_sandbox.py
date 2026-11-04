"""Local failure observation only; never a signer input or production package.

Drain child output without storing it. Retain only a bounded tail internally;
export boolean hints and independently observed filesystem capacity on failure.
"""
def diagnostic_run(arguments, *, timeout=600):
    import json,re,selectors,time
    process=start(arguments,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    selector=selectors.DefaultSelector();selector.register(process.stdout,selectors.EVENT_READ)
    end=time.monotonic()+timeout;tail=b''
    try:
        while selector.get_map():
            if time.monotonic()>=end:raise Refused('COMMAND_TIMEOUT')
            for key,_ in selector.select(min(1,max(0,end-time.monotonic()))):
                raw=os.read(key.fileobj.fileno(),8192)
                if raw:tail=(tail+raw)[-32768:]
                else:selector.unregister(key.fileobj)
        code=process.wait(timeout=max(.1,end-time.monotonic()))
        if code:
            capacity=os.statvfs('/work')
            observation={'scope':'untrusted-output-hints-plus-observed-capacity','exit_code':code,
                         'work_free_bytes':capacity.f_bavail*capacity.f_frsize,
                         'work_total_bytes':capacity.f_blocks*capacity.f_frsize,
                         'no_space_hint':b'No space left on device' in tail or b'os error 28' in tail,
                         'test_failure_hint':b'test result: FAILED' in tail,
                         'compilation_failure_hint':b'could not compile' in tail,
                         'killed_hint':b'SIGKILL' in tail or b'signal: 9' in tail,
                         'failed_tests':sorted(set(x.decode('ascii') for x in re.findall(rb'test ([A-Za-z_][A-Za-z0-9_:]{0,160}) \.\.\. FAILED',tail)))[:32],
                         'permission_denied_hint':b'Permission denied' in tail,
                         'connection_refused_hint':b'Connection refused' in tail,
                         'missing_file_hint':b'No such file or directory' in tail,
                         'missing_environment_hint':b'NotPresent' in tail}
            os.write(2,(json.dumps(observation,sort_keys=True)+'\n').encode())
        return code
    finally:
        selector.close();process.stdout.close();stop(process)

run=diagnostic_run
