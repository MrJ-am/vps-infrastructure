/* This probe runs only in disposable VMs against the dedicated synthetic victim.
 * It links the identical confinement.o used by the shipped collector launcher. */
#define _GNU_SOURCE
#include "confinement.h"
#include "broker.h"
#include <errno.h>
#include <fcntl.h>
#include <linux/capability.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/syscall.h>
#include <sys/uio.h>
#include <unistd.h>

static void check(int success, const char *code) {
    if (!success) { printf("PROBE_FAILED:%s:%d\n", code, errno); exit(1); }
}

static void file_probe(const char *path, uintptr_t address, int restricted, const char *token) {
    errno = 0;
    int fd = open(path, O_RDONLY | O_CLOEXEC);
    if (restricted) {
        check(fd == -1 && errno == EACCES, "PROC_READ_OPEN_DENIAL");
        return;
    }
    check(fd >= 0, "PROC_READ_CONTROL_OPEN");
    char data[4096];
    ssize_t length = address ? pread(fd, data, 1, (off_t)address) : read(fd, data, sizeof(data));
    check(length > 0, "PROC_READ_CONTROL_BYTES");
    if (address) check(data[0] == 'S', "PROC_READ_CONTROL_SENTINEL");
    else check(memmem(data, (size_t)length, token, strlen(token)) != NULL, "PROC_READ_CONTROL_TOKEN");
    close(fd);
}

int main(int argc, char **argv) {
    check(argc == 6, "ARGUMENTS");
    int mode = atoi(argv[1]); /* 0: V1 control, 1: new seccomp only, 2: full. */
    char *end = NULL;
    long pid = strtol(argv[2], &end, 10);
    check(end && *end == '\0' && pid > 1 && pid < 2147483647, "SYNTHETIC_PID");
    uintptr_t address = (uintptr_t)strtoull(argv[3], &end, 10);
    check(end && *end == '\0' && address > 0 && mode >= 0 && mode <= 3, "SYNTHETIC_ADDRESS");
    long proc_pid = strtol(argv[4], &end, 10);
    check(end && *end == '\0' && proc_pid > 1 && proc_pid < 2147483647, "SYNTHETIC_ROOT_PID");
    uintptr_t proc_address = (uintptr_t)strtoull(argv[5], &end, 10);
    check(end && *end == '\0' && proc_address > 0, "SYNTHETIC_ROOT_ADDRESS");
    if (mode != 0 && mode != 3) check(mrj_start_exe_broker() == 0, "EXE_BROKER_SETUP");
    if (mode == 1) check(mrj_drop_caps() == 0, "CAPABILITIES_DROPPED");
    if (mode == 2) {
        check(mrj_confine() == 0, "LANDLOCK_SETUP");
        /* As in collect-confined, exec a store executable after restriction.
         * Prove that UID 0 does not regain capabilities and Landlock persists. */
        execl(argv[0], argv[0], "3", argv[2], argv[3], argv[4], argv[5], (char *)NULL);
        check(0, "POST_CONFINEMENT_EXEC");
    }
    if (mode == 3) mode = 2;
    if (mode != 0) {
        struct __user_cap_header_struct header = { .version = _LINUX_CAPABILITY_VERSION_3, .pid = 0 };
        struct __user_cap_data_struct caps[2];
        check(syscall(SYS_capget, &header, caps) == 0 && caps[0].effective == 0 && caps[1].effective == 0
            && caps[0].permitted == 0 && caps[1].permitted == 0, "READER_HAS_NO_CAPABILITIES");
    }

    char byte = 0;
    struct iovec local = { .iov_base = &byte, .iov_len = 1 };
    struct iovec remote = { .iov_base = (void *)address, .iov_len = 1 };
    errno = 0;
    ssize_t count = syscall(SYS_process_vm_readv, pid, &local, 1, &remote, 1, 0);
    if (mode == 0) check(count == 1 && byte == 'S', "VM_READ_CONTROL");
    else check(count == -1 && errno == EPERM, "VM_READ_SECCOMP_DENIAL");
    byte = 'S'; /* A successful control writes the original value only. */
    errno = 0;
    count = syscall(SYS_process_vm_writev, pid, &local, 1, &remote, 1, 0);
    if (mode == 0) check(count == 1, "VM_WRITE_CONTROL");
    else check(count == -1 && errno == EPERM, "VM_WRITE_SECCOMP_DENIAL");

    char path[256];
    const char *entries[] = { "mem", "environ", "cmdline" };
    const char *tokens[] = { "", "SYNTHETIC_ENV_ONLY", "SYNTHETIC_ARG_ONLY" };
    for (unsigned index = 0; index < 3; ++index) {
        snprintf(path, sizeof(path), "/proc/%ld/%s", proc_pid, entries[index]);
        file_probe(path, index == 0 ? proc_address : 0, mode == 2, tokens[index]);
        snprintf(path, sizeof(path), "/proc/%ld/task/%ld/%s", proc_pid, proc_pid, entries[index]);
        file_probe(path, index == 0 ? proc_address : 0, mode == 2, tokens[index]);
        snprintf(path, sizeof(path), "/proc/%ld/root/proc/%ld/%s", proc_pid, proc_pid, entries[index]);
        file_probe(path, index == 0 ? proc_address : 0, mode == 2, tokens[index]);
    }
    snprintf(path, sizeof(path), "/proc/%ld/mem", proc_pid);
    errno = 0;
    int writable = open(path, O_WRONLY | O_CLOEXEC);
    if (mode == 2) check(writable == -1 && errno == EACCES, "PROC_WRITE_OPEN_DENIAL");
    else {
        check(writable >= 0 && pwrite(writable, "S", 1, (off_t)proc_address) == 1, "PROC_WRITE_CONTROL");
        close(writable);
    }
    /* O_PATH itself is metadata only; reopening the descriptor must still
     * enforce Landlock rather than create a proc/self/fd escape. */
    int metadata = open(path, O_PATH | O_CLOEXEC);
    check(metadata >= 0, "PROC_METADATA_ONLY_PATH");
    snprintf(path, sizeof(path), "/proc/self/fd/%d", metadata);
    file_probe(path, proc_address, mode == 2, "");
    close(metadata);
    snprintf(path, sizeof(path), "/proc/%ld/exe", pid);
    char executable[4096];
    count = mode == 0 ? readlink(path, executable, sizeof(executable) - 1)
        : mrj_exe_link((uint32_t)pid, executable, sizeof(executable));
    check(count > 0, "CROSS_UID_EXE_READLINK");
    executable[count] = '\0';
    check(strncmp(executable, "/nix/store/", 11) == 0 && strstr(executable, "/bin/synthetic-victim"), "EXE_VALUE");

    if (mode != 0) {
        errno = 0;
        check(syscall(SYS_pidfd_getfd, -1, 0, 0) == -1 && errno == EPERM, "PIDFD_GETFD_DENIAL");
        errno = 0;
        check(syscall(SYS_ptrace, 0, 0, 0, 0) == -1 && errno == EPERM, "PTRACE_DENIAL");
    }
    for (unsigned i = 0; i < 3; ++i) {
        const char *private_paths[] = { "/var/lib/synthetic-observer-private", "/run/credentials/synthetic-observer-private", "/etc/shadow" };
        int fd = open(private_paths[i], O_RDONLY | O_CLOEXEC);
        check(fd == -1, "PRIVATE_FILE_DENIAL");
    }
    int network = socket(AF_INET, SOCK_STREAM, 0);
    check(network == -1, "INET_DENIAL");
    int write = open("/etc/synthetic-observer-write", O_WRONLY | O_CREAT | O_CLOEXEC, 0600);
    check(write == -1, "SYSTEM_WRITE_DENIAL");
    /* Keep the exact transient unit observable for resource/property checks. */
    sleep(3);
    printf("{\"mode\":%d,\"readlink_exe\":true,\"memory_syscalls_denied\":%s,\"proc_files_denied\":%s,\"proc_aliases_checked\":true,\"private_files_network_and_writes_denied\":true,\"proc_subject\":\"synthetic-root\",\"memory_syscall_subject\":\"synthetic-foreign-uid\"}\n",
           mode, mode ? "true" : "false", mode == 2 ? "true" : "false");
    return 0;
}
