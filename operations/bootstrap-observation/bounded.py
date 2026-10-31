"""Bounded subprocess capture for fixed commands; no shell, raw errors or output files."""
import os
import selectors
import signal
import subprocess
import time


class Refused(Exception):
    pass


def run(argv, *, environment, seconds, limit=8192, input_bytes=None):
    if input_bytes is not None and len(input_bytes) > limit:
        raise Refused()
    child = subprocess.Popen(
        argv, env=environment, stdin=subprocess.PIPE if input_bytes is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, start_new_session=True,
        close_fds=True,
    )
    output = bytearray()
    deadline = time.monotonic() + seconds
    selector = selectors.DefaultSelector()
    try:
        if input_bytes is not None:
            # Input is <= 8 KiB and consumed by the pinned validator. Use
            # nonblocking I/O so a failed child cannot block its supervisor.
            os.set_blocking(child.stdin.fileno(), False)
            selector.register(child.stdin, selectors.EVENT_WRITE, memoryview(input_bytes))
        os.set_blocking(child.stdout.fileno(), False)
        selector.register(child.stdout, selectors.EVENT_READ)
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise Refused()
            for key, _ in selector.select(remaining):
                if key.events == selectors.EVENT_WRITE:
                    pending = key.data
                    if pending:
                        written = os.write(key.fd, pending)
                        pending = pending[written:]
                    if pending:
                        selector.modify(key.fileobj, selectors.EVENT_WRITE, pending)
                    else:
                        selector.unregister(key.fileobj)
                        key.fileobj.close()
                else:
                    chunk = os.read(key.fd, min(4096, limit + 1 - len(output)))
                    if not chunk:
                        selector.unregister(key.fileobj)
                    else:
                        output.extend(chunk)
                        if len(output) > limit:
                            raise Refused()
        remaining = deadline - time.monotonic()
        if remaining <= 0 or child.wait(timeout=remaining) != 0:
            raise Refused()
        return bytes(output)
    except Exception:
        raise Refused() from None
    finally:
        selector.close()
        # The transient unit has its own deadline and cgroup cleanup. This
        # additionally terminates local helpers, including children retaining stdout.
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            child.wait(timeout=1)
        except subprocess.TimeoutExpired:
            pass
        for stream in (child.stdin, child.stdout):
            if stream is not None:
                stream.close()
