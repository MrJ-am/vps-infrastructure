"""One fixed native fast-forward merge request; no general write transport."""
import http.client
import json
import re
import socket
import threading
import time


class Refused(RuntimeError):
    pass


def merge(token, head):
    if not re.fullmatch(r"[0-9a-f]{40}",token) or not re.fullmatch(r"[0-9a-f]{40}",head):
        raise Refused("MERGE_INPUT_REFUSED")
    body=json.dumps({'Do':'fast-forward-only','head_commit_id':head,'force_merge':True,
        'merge_when_checks_succeed':False,'delete_branch_after_merge':False},sort_keys=True).encode()
    connection=http.client.HTTPConnection('127.0.0.1',3004,timeout=5)
    timer=response=None
    end=time.monotonic()+15
    try:
        connection.connect();owned=connection.sock
        def expire():
            try:owned.shutdown(socket.SHUT_RDWR)
            except OSError:pass
        timer=threading.Timer(max(0,end-time.monotonic()),expire);timer.daemon=True;timer.start()
        connection.request('POST','/api/v1/repos/MrJ-am/mrjam-validation/pulls/1/merge',body=body,
            headers={'Authorization':'token '+token,'Content-Type':'application/json','Accept-Encoding':'identity',
                     'User-Agent':'mrjam-rules-bootstrap-adoption/1'})
        response=connection.getresponse()
        raw=response.read(8193)
        if response.status!=200 or len(raw)>8192 or time.monotonic()>=end:
            raise Refused("MERGE_HTTP_REFUSED")
    except Refused:
        raise
    except Exception:
        raise Refused("MERGE_HTTP_REFUSED") from None
    finally:
        if timer is not None:timer.cancel()
        if response is not None:response.close()
        connection.close()
