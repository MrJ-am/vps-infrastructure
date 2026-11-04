"""Publish already verified control documents, with the admission record last.

This is filesystem machinery, not an admission decision or a candidate API.
The installed caller must resolve its fixed record against its protected anchor.
"""
import fcntl
import os
import re
import secrets
import stat


def require(condition):
    if not condition:
        raise ValueError('ADMISSION_PUBLICATION_REFUSED')


def directory(path, owner):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        info = os.fstat(fd)
        require(info.st_uid == owner and not info.st_mode & 0o022)
        return fd
    except BaseException:
        os.close(fd)
        raise


def immutable(fd, name, raw, owner):
    """No overwrite: an existing different or unsafe file is an error."""
    require(type(raw) is bytes and 0 < len(raw) <= 262144)
    temporary = '.publish-' + secrets.token_hex(16)
    child = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    0o600, dir_fd=fd)
    try:
        with os.fdopen(child, 'wb') as output:
            output.write(raw)
            output.flush()
            os.fchmod(output.fileno(), 0o444)
            os.fsync(output.fileno())
        try:
            os.link(temporary, name, src_dir_fd=fd, dst_dir_fd=fd,
                    follow_symlinks=False)
        except FileExistsError:
            existing = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                               dir_fd=fd)
            try:
                info = os.fstat(existing)
                require(stat.S_ISREG(info.st_mode) and info.st_uid == owner
                        and stat.S_IMODE(info.st_mode) == 0o444 and info.st_nlink == 1
                        and info.st_size == len(raw) and os.read(existing, len(raw)+1) == raw)
            finally:
                os.close(existing)
    finally:
        os.unlink(temporary, dir_fd=fd)
        os.fsync(fd)


def recover(fd, owner):
    # Only this publisher's interrupted temporary links, under its global lock.
    for name in os.listdir(fd):
        if not re.fullmatch(r'\.publish-[0-9a-f]{32}', name):
            continue
        info = os.stat(name, dir_fd=fd, follow_symlinks=False)
        require(stat.S_ISREG(info.st_mode) and info.st_uid == owner
                and stat.S_IMODE(info.st_mode) in (0o600, 0o444)
                and info.st_nlink in (1, 2) and info.st_size <= 262144)
        os.unlink(name, dir_fd=fd)
    os.fsync(fd)


def publish(path, proposal, record, metadata, *, owner=0, document_count=8):
    require(os.getuid() == owner and re.fullmatch('[0-9a-f]{64}', proposal)
            and type(record) is bytes and 0 < len(record) <= 16384
            and type(document_count) is int and document_count in (7,8)
            and len(metadata) == document_count
            and all(re.fullmatch('[0-9a-f]{64}\\.data', name) for name in metadata))
    root = directory(path, owner)
    try:
        fcntl.flock(root, fcntl.LOCK_EX)
        recover(root, owner)
        try:
            os.mkdir('metadata', 0o755, dir_fd=root)
            os.fsync(root)
        except FileExistsError:
            pass
        # Opening relative to the checked descriptor avoids a pathname swap.
        child = os.open('metadata', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                        dir_fd=root)
        try:
            info = os.fstat(child)
            require(info.st_uid == owner and not info.st_mode & 0o022)
            recover(child, owner)
            for name, raw in sorted(metadata.items()):
                immutable(child, name, raw, owner)
        finally:
            os.close(child)
        immutable(root, proposal + '.json', record, owner)
    finally:
        os.close(root)
