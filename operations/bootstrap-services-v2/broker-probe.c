/* Disposable-VM canary only. Never included in the production closure.
 * The filter object and protocol server are identical to the shipped launcher. */
#define _GNU_SOURCE
#include "broker.h"
#include <errno.h>
#include <fcntl.h>
#include <linux/openat2.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/syscall.h>
#include <sys/uio.h>
#include <sys/wait.h>
#include <unistd.h>

static void check(int yes, const char *code) {
    if (!yes) { printf("BROKER_PROBE_FAILED:%s:%d\n", code, errno); exit(1); }
}

int main(int argc, char **argv) {
    check(argc == 6, "ARGUMENTS");
    int legacy = strcmp(argv[1], "0") == 0;
    long pid = strtol(argv[2], NULL, 10), root_pid = strtol(argv[4], NULL, 10);
    uintptr_t address = strtoull(argv[3], NULL, 10), root_address = strtoull(argv[5], NULL, 10);
    check(pid > 1 && root_pid > 1 && address && root_address, "FIXTURE");
    char paths[4][128], executable[128], alias[128];
    snprintf(executable, sizeof(executable), "/proc/%ld/exe", pid);
    const char *names[] = {"mem", "environ", "cmdline"};
    const char *tokens[] = {"", "SYNTHETIC_ENV_ONLY", "SYNTHETIC_ARG_ONLY"};
    for (unsigned i = 0; i < 3; ++i) {
        snprintf(paths[i], sizeof(paths[i]), "/proc/%ld/%s", root_pid, names[i]);
        int fd = open(paths[i], O_RDONLY | O_CLOEXEC);
        check(fd >= 0, "POSITIVE_FILE_OPEN");
        char data[4096];
        ssize_t n = i ? read(fd, data, sizeof(data)) : pread(fd, data, 1, root_address);
        check(n > 0 && (i ? memmem(data, n, tokens[i], strlen(tokens[i])) != NULL : data[0] == 'S'), "POSITIVE_FILE_CONTENT");
        close(fd);
    }
    snprintf(paths[3], sizeof(paths[3]), "/proc/%ld/root/proc/%ld/mem", root_pid, root_pid);
    char byte = 0;
    struct iovec local = {&byte, 1}, remote = {(void *)address, 1};
    ssize_t n = syscall(SYS_process_vm_readv, pid, &local, 1, &remote, 1, 0);
    check(legacy ? n == 1 && byte == 'S' : n == -1 && errno == EPERM, "MEMORY_READ_CONTROL");
    byte = 'S';
    n = syscall(SYS_process_vm_writev, pid, &local, 1, &remote, 1, 0);
    check(legacy ? n == 1 : n == -1 && errno == EPERM, "MEMORY_WRITE_CONTROL");
    int pair[2];
    check(socketpair(AF_UNIX, SOCK_SEQPACKET, 0, pair) == 0, "PAIR");
    pid_t child = fork(); check(child >= 0, "FORK");
    if (child == 0) {
        close(pair[0]);
        if (dup2(pair[1], MRJ_EXE_FD) < 0) _exit(80);
        if (pair[1] != MRJ_EXE_FD) close(pair[1]);
        /* Deliberately retain a readable synthetic mem fd to test descriptor
         * syscalls too. The real broker closes all inherited fds instead. */
        int retained = open(paths[0], O_RDONLY);
        if (retained < 4) _exit(81);
        snprintf(alias, sizeof(alias), "/proc/self/fd/%d", retained);
        close(0); close(1); close(2);
        if (mrj_restrict_exe_broker()) _exit(82);
        uint64_t failures = 0; unsigned tested = 0;
#define DENIED(call) do { errno = 0; long r = (call); if (r != -1 || errno != EPERM) failures |= (1ULL << tested); ++tested; } while (0)
        DENIED(syscall(SYS_process_vm_readv, pid, &local, 1, &remote, 1, 0));
        DENIED(syscall(SYS_process_vm_writev, pid, &local, 1, &remote, 1, 0));
        for (unsigned i = 0; i < 4; ++i) DENIED(syscall(SYS_openat, AT_FDCWD, paths[i], O_RDONLY, 0));
        DENIED(syscall(SYS_open, paths[0], O_RDONLY, 0));
        struct open_how how = {.flags = O_RDONLY};
        DENIED(syscall(SYS_openat2, AT_FDCWD, paths[0], &how, sizeof(how)));
        DENIED(syscall(SYS_openat, AT_FDCWD, paths[0], O_WRONLY, 0));
        DENIED(syscall(SYS_openat, AT_FDCWD, alias, O_RDONLY, 0));
        DENIED(syscall(SYS_read, retained, &byte, 1));
        DENIED(syscall(SYS_pread64, retained, &byte, 1, root_address));
        DENIED(syscall(SYS_write, retained, &byte, 1));
        DENIED(syscall(SYS_pwrite64, retained, &byte, 1, root_address));
        DENIED(syscall(SYS_ptrace, 2, pid, address, 0));
        DENIED(syscall(SYS_pidfd_getfd, -1, 0, 0));
        DENIED(syscall(SYS_io_uring_setup, 0, NULL));
        DENIED(syscall(SYS_dup, retained));
        DENIED(syscall(SYS_socket, AF_INET, SOCK_STREAM, 0));
        DENIED(syscall(SYS_execve, executable, NULL, NULL));
        DENIED(syscall(SYS_mmap, NULL, 4096, 1, 2, retained, 0));
        DENIED(syscall(SYS_recvfrom, retained, &byte, 1, MSG_DONTWAIT, NULL, NULL));
        DENIED(syscall(SYS_sendto, retained, &byte, 1, MSG_NOSIGNAL, NULL, 0));
        DENIED(syscall(SYS_sendto, MRJ_EXE_FD, &byte, 1, MSG_NOSIGNAL, (void *)(1ULL << 32), 0));
        char link[4096];
        long length = syscall(SYS_readlinkat, AT_FDCWD, executable, link, sizeof(link)-1);
        if (length <= 0) failures |= (1ULL << 63);
        else { link[length] = 0; if (!strstr(link, "/bin/synthetic-victim")) failures |= (1ULL << 63); }
        uint64_t result[] = {failures, tested};
        if (send(MRJ_EXE_FD, result, sizeof(result), MSG_NOSIGNAL) != sizeof(result)) _exit(83);
        _exit(0);
    }
    close(pair[1]);
    uint64_t result[2]; int status;
    check(recv(pair[0], result, sizeof(result), MSG_TRUNC) == sizeof(result), "RESULT");
    close(pair[0]);
    check(waitpid(child, &status, 0) == child && WIFEXITED(status) && WEXITSTATUS(status) == 0, "CHILD_EXIT");
    check(result[0] == 0 && result[1] == 24, "BROKER_FILTER_AND_EXE");

    check(mrj_start_exe_broker() == 0, "PROTOCOL_START");
    for (unsigned i = 0; i < 14; ++i) {
        uint32_t request[2] = {(uint32_t)pid, 0}; size_t length = sizeof(uint32_t);
        if (i == 0) length = 3;
        if (i == 1) length = sizeof(request);
        if (i == 2) request[0] = 0;
        if (i == 3) request[0] = 2147483648u;
        struct mrj_exe_response response;
        check(send(MRJ_EXE_FD, request, length, MSG_NOSIGNAL) == (ssize_t)length, "PROTOCOL_SEND");
        check(recv(MRJ_EXE_FD, &response, sizeof(response), MSG_TRUNC) == sizeof(response), "PROTOCOL_RECEIVE");
        if (i < 4) {
            check(response.code == 1 && response.length == 0, "PROTOCOL_REJECT");
            for (unsigned j = 0; j < sizeof(response.path); ++j) check(response.path[j] == 0, "PROTOCOL_EMPTY_ERROR");
        } else {
            check(response.code == 0 && response.length > 0 && response.length < MRJ_EXE_MAX, "PROTOCOL_VALID_EXE");
            check(strstr(response.path, "/bin/synthetic-victim") != NULL, "PROTOCOL_EXE_VALUE");
            for (unsigned j = response.length; j < MRJ_EXE_MAX; ++j) check(response.path[j] == 0, "PROTOCOL_ZERO_PADDING");
        }
    }
    check(recv(MRJ_EXE_FD, &byte, 1, 0) == 0, "PROTOCOL_FINITE_14");
    close(MRJ_EXE_FD);
    check(waitpid(-1, &status, 0) > 0 && WIFEXITED(status) && WEXITSTATUS(status) == 0, "SERVER_EXIT");
    sleep(3);
    puts("{\"broker_denials\":24,\"readlink_exe\":true,\"positive_controls\":true,\"malformed_protocol_refused\":true,\"request_limit\":14}");
    return 0;
}
