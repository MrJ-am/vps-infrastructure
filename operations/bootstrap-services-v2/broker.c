#define _GNU_SOURCE
#include "broker.h"
#include <errno.h>
#include <fcntl.h>
#include <linux/audit.h>
#include <linux/filter.h>
#include <linux/seccomp.h>
#include <signal.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include <sys/prctl.h>
#include <sys/socket.h>
#include <sys/syscall.h>
#include <unistd.h>

#define LD(field) BPF_STMT(BPF_LD | BPF_W | BPF_ABS, offsetof(struct seccomp_data, field))
#define RET(value) BPF_STMT(BPF_RET | BPF_K, value)
#define EQ(value, yes, no) BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, value, yes, no)

int mrj_restrict_exe_broker(void) {
    /* No open/openat/openat2, exec, ptrace, process_vm_*, pidfd_getfd,
     * io_uring, mmap, dup, network socket, arbitrary read/write or inherited
     * descriptor access. Only exe readlink and the private fd 3 protocol. */
    struct sock_filter filter[] = {
        LD(arch), EQ(AUDIT_ARCH_X86_64, 1, 0), RET(SECCOMP_RET_KILL_PROCESS),
        LD(nr),
        EQ(SYS_readlinkat, 0, 1), RET(SECCOMP_RET_ALLOW),
        EQ(SYS_exit, 0, 1), RET(SECCOMP_RET_ALLOW),
        EQ(SYS_exit_group, 0, 1), RET(SECCOMP_RET_ALLOW),
        EQ(SYS_recvfrom, 0, 3),
        LD(args[0]), EQ(MRJ_EXE_FD, 0, 1), RET(SECCOMP_RET_ALLOW),
        LD(nr), EQ(SYS_sendto, 0, 7),
        LD(args[0]), EQ(MRJ_EXE_FD, 0, 5),
        LD(args[4]), EQ(0, 0, 3),
        BPF_STMT(BPF_LD | BPF_W | BPF_ABS, offsetof(struct seccomp_data, args[4]) + 4),
        EQ(0, 0, 1), RET(SECCOMP_RET_ALLOW),
        RET(SECCOMP_RET_ERRNO | EPERM),
    };
    struct sock_fprog program = { .len = (unsigned short)(sizeof(filter)/sizeof(filter[0])), .filter = filter };
    if (prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0)) return -1;
    return prctl(PR_SET_SECCOMP, SECCOMP_MODE_FILTER, &program);
}

static void serve(void) {
    for (unsigned request = 0; request < 14; ++request) {
        uint32_t pid = 0;
        ssize_t count = recv(MRJ_EXE_FD, &pid, sizeof(pid), MSG_TRUNC);
        if (count == 0) _exit(0);
        struct mrj_exe_response response = {0};
        response.code = 1;
        if (count == sizeof(pid) && pid > 0 && pid < 2147483648u) {
            char path[32] = "/proc/";
            char digits[10]; unsigned length = 0;
            do { digits[length++] = (char)('0' + pid % 10); pid /= 10; } while (pid);
            for (unsigned i = 0; i < length; ++i) path[6+i] = digits[length-i-1];
            memcpy(path+6+length, "/exe", 5);
            count = syscall(SYS_readlinkat, AT_FDCWD, path, response.path, MRJ_EXE_MAX);
            if (count > 0 && count < MRJ_EXE_MAX) {
                response.code = 0; response.length = (uint32_t)count;
            } else memset(response.path, 0, sizeof(response.path));
        }
        if (send(MRJ_EXE_FD, &response, sizeof(response), MSG_NOSIGNAL) != sizeof(response)) _exit(78);
    }
    _exit(0);
}

int mrj_start_exe_broker(void) {
    if (syscall(SYS_close_range, 3u, ~0u, 0u)) return -1;
    int pair[2];
    if (socketpair(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC, 0, pair)) return -1;
    pid_t owner = getpid();
    pid_t child = fork();
    if (child < 0) { close(pair[0]); close(pair[1]); return -1; }
    if (child == 0) {
        close(pair[0]);
        if (dup2(pair[1], MRJ_EXE_FD) < 0) _exit(78);
        if (pair[1] != MRJ_EXE_FD) close(pair[1]);
        close(0); close(1); close(2);
        if (prctl(PR_SET_PDEATHSIG, SIGKILL) || getppid() != owner || mrj_restrict_exe_broker()) _exit(78);
        serve();
    }
    close(pair[1]);
    if (pair[0] != MRJ_EXE_FD && dup2(pair[0], MRJ_EXE_FD) < 0) return -1;
    if (pair[0] != MRJ_EXE_FD) close(pair[0]);
    if (fcntl(MRJ_EXE_FD, F_SETFD, 0)) return -1;
    return 0;
}

int mrj_exe_link(uint32_t pid, char *output, unsigned maximum) {
    struct mrj_exe_response response;
    if (send(MRJ_EXE_FD, &pid, sizeof(pid), MSG_NOSIGNAL) != sizeof(pid)) return -1;
    if (recv(MRJ_EXE_FD, &response, sizeof(response), MSG_TRUNC) != sizeof(response)) return -1;
    if (response.code || response.length == 0 || response.length >= maximum || response.length >= MRJ_EXE_MAX) return -1;
    memcpy(output, response.path, response.length);
    output[response.length] = '\0';
    return (int)response.length;
}
