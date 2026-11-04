"""Read-only, fixed-generation TCP listener classification; no process data."""
import ipaddress
import json
import os
from pathlib import Path
import re
import resource
import signal
import stat
import sys

PROMOTED = '/nix/store/dc09bjfaf8wsfrwxpkqw0bi3xhp3nklm-nixos-system-srv1982677-26.05pre-git'
RESULT = '/run/mrjam-first-release-status-05/result.json'
EXPECTED = frozenset((22, 80, 443, 2222))
PRIVATE = frozenset((3002, 3004, 5432, 8443, 38101, 38102))
MAX_BYTES = 262144
MAX_ROWS = 2048
MAX_PORTS = 64


class Refused(RuntimeError):
    pass


def require(value):
    if not value:
        raise Refused()


def read_fixed(path, maximum, private=False):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode))
        if private:
            require(info.st_uid == info.st_gid == 0 and info.st_nlink == 1
                    and stat.S_IMODE(info.st_mode) == 0o600)
        data = bytearray()
        while len(data) <= maximum:
            part = os.read(fd, min(16384, maximum + 1 - len(data)))
            if not part:
                break
            data.extend(part)
        require(len(data) <= maximum)
        return bytes(data)
    finally:
        os.close(fd)


def address_class(address):
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        return 'mapped_loopback' if address.ipv4_mapped.is_loopback else 'mapped_nonloopback'
    if address.is_loopback:
        return 'loopback'
    if address.is_unspecified:
        return 'wildcard'
    if address.is_link_local:
        return 'link_local'
    return 'specific_nonloopback'


def parse(raw, ipv6=False):
    require(type(raw) is bytes and len(raw) <= MAX_BYTES)
    lines = raw.decode('ascii', 'strict').splitlines()
    require(lines and len(lines) <= MAX_ROWS + 1)
    header = lines[0].split()
    require(header[:4] == ['sl', 'local_address', 'remote_address' if ipv6 else 'rem_address', 'st'])
    result = []
    width = 32 if ipv6 else 8
    for line in lines[1:]:
        fields = line.split()
        require(len(fields) >= 4 and re.fullmatch('[0-9A-F]{2}', fields[3]))
        if fields[3] != '0A':
            continue
        require(re.fullmatch('[0-9A-F]{' + str(width) + '}:[0-9A-F]{4}', fields[1]))
        address, port = fields[1].split(':')
        data = bytes.fromhex(address)
        data = b''.join(data[i:i+4][::-1] for i in range(0, len(data), 4))
        ip = ipaddress.ip_address(data)
        require(ip.version == (6 if ipv6 else 4))
        number = int(port, 16)
        require(1 <= number <= 65535)
        result.append((number, 'ipv6' if ipv6 else 'ipv4', address_class(ip)))
    return result


def classify(rows):
    require(len(rows) <= 2 * MAX_ROWS)
    ports = sorted({port for port, _, _ in rows})
    require(len(ports) <= MAX_PORTS)
    nonloopback = {port for port, _, kind in rows if kind not in ('loopback', 'mapped_loopback')}
    unexpected = sorted(nonloopback - EXPECTED)
    return {
        'schema_version': 1, 'code': 'TCP_LISTENERS_CLASSIFIED',
        'nonloopback_is_not_a_reachability_claim': True,
        'expected_public_ports_present': {str(port): port in nonloopback for port in sorted(EXPECTED)},
        'unexpected_nonloopback_ports': unexpected,
        'only_unexpected_nonloopback_is_llmnr_port': unexpected == [5355],
        'private_application_ports_loopback_only': not bool(PRIVATE & nonloopback),
        'listeners': [{'port': port,
                       'role': 'expected_public' if port in EXPECTED else 'private_application' if port in PRIVATE
                               else 'dns_stub' if port == 53 else 'llmnr_port' if port == 5355 else 'other_port',
                       'bindings': [{'family': family, 'address_class': kind,
                                     'count': sum(row == (port, family, kind) for row in rows)}
                                    for family, kind in sorted({(family, kind) for p, family, kind in rows if p == port})]}
                      for port in ports],
        'process_data_read': False, 'addresses_exported': False,
        'application_data_read': False, 'production_mutation': False,
    }


def collect():
    require(all(os.path.realpath(path) == PROMOTED for path in ('/run/current-system', '/nix/var/nix/profiles/system')))
    require(json.loads(read_fixed(RESULT, 1024, private=True)) == {
        'schema_version': 1, 'code': 'CUTOVER_VERIFIED', 'phase': 'public-writes-open'})
    return classify(parse(read_fixed('/proc/net/tcp', MAX_BYTES))
                    + parse(read_fixed('/proc/net/tcp6', MAX_BYTES), ipv6=True))


def main():
    if len(sys.argv) != 1 or os.geteuid() != 0 or os.uname().nodename != 'srv1982677':
        return 64
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(Refused()))
    signal.alarm(10)
    try:
        value = collect()
        code = 0
    except Exception:
        value = {'schema_version': 1, 'code': 'TCP_LISTENER_CLASSIFICATION_REFUSED'}
        code = 1
    finally:
        signal.alarm(0)
    print(json.dumps(value, sort_keys=True, separators=(',', ':')))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
