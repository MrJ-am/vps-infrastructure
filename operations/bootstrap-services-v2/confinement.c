#define _GNU_SOURCE
#include "confinement.h"
#include <errno.h>
#include <fcntl.h>
#include <linux/landlock.h>
#include <linux/capability.h>
#include <stdint.h>
#include <sys/prctl.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <unistd.h>

static int allow_path(int rules, const char *path, uint64_t access, int optional) {
    int fd = open(path, O_PATH | O_CLOEXEC);
    if (fd < 0) return optional && errno == ENOENT ? 0 : -1;
    struct stat info;
    if (fstat(fd, &info) || info.st_uid != 0 ||
        (info.st_mode & (S_ISDIR(info.st_mode) ? 0002 : 0022))) {
        close(fd);
        return -1;
    }
    struct landlock_path_beneath_attr rule = { .allowed_access = access, .parent_fd = fd };
    int result = (int)syscall(SYS_landlock_add_rule, rules, LANDLOCK_RULE_PATH_BENEATH, &rule, 0);
    close(fd);
    return result;
}

int mrj_drop_caps(void) {
    if (prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0)) return -1;
    struct __user_cap_header_struct capabilities = { .version = _LINUX_CAPABILITY_VERSION_3, .pid = 0 };
    struct __user_cap_data_struct empty[2] = {{0}, {0}};
    return syscall(SYS_capset, &capabilities, empty) || prctl(PR_CAP_AMBIENT, PR_CAP_AMBIENT_CLEAR_ALL, 0, 0, 0) ? -1 : 0;
}

int mrj_confine(void) {
    /* fd 3 belongs only to the exe broker, created after closing inherited fds.
     * The collector drops ptrace itself; the broker has no file-opening syscall. */
    if (syscall(SYS_close_range, 4u, ~0u, 0u)) return -1;
    int input = open("/dev/null", O_RDONLY | O_CLOEXEC);
    if (input < 0) return -1;
    if (dup2(input, STDIN_FILENO) < 0) { close(input); return -1; }
    if (input != STDIN_FILENO) close(input);
    if (mrj_drop_caps()) return -1;
    long abi = syscall(SYS_landlock_create_ruleset, NULL, 0, LANDLOCK_CREATE_RULESET_VERSION);
    /* ABI 3 covers file reads/writes and truncation. No degraded fallback. */
    if (abi < 3) return -1;
    uint64_t reads = LANDLOCK_ACCESS_FS_READ_FILE | LANDLOCK_ACCESS_FS_READ_DIR;
    struct landlock_ruleset_attr rule = { .handled_access_fs =
        LANDLOCK_ACCESS_FS_EXECUTE | LANDLOCK_ACCESS_FS_WRITE_FILE | reads |
        LANDLOCK_ACCESS_FS_REMOVE_DIR | LANDLOCK_ACCESS_FS_REMOVE_FILE |
        LANDLOCK_ACCESS_FS_MAKE_CHAR | LANDLOCK_ACCESS_FS_MAKE_DIR |
        LANDLOCK_ACCESS_FS_MAKE_REG | LANDLOCK_ACCESS_FS_MAKE_SOCK |
        LANDLOCK_ACCESS_FS_MAKE_FIFO | LANDLOCK_ACCESS_FS_MAKE_BLOCK |
        LANDLOCK_ACCESS_FS_MAKE_SYM | LANDLOCK_ACCESS_FS_REFER | LANDLOCK_ACCESS_FS_TRUNCATE };
    int rules = (int)syscall(SYS_landlock_create_ruleset, &rule, sizeof(rule), 0);
    if (rules < 0) return -1;
    int failed = allow_path(rules, "/nix/store", reads | LANDLOCK_ACCESS_FS_EXECUTE, 0);
    const char *files[] = { "/etc/passwd", "/etc/group", "/etc/nsswitch.conf", "/etc/machine-id",
                           "/etc/ld.so.cache", "/etc/os-release" };
    for (unsigned i = 0; i < sizeof(files) / sizeof(files[0]); ++i)
        if (allow_path(rules, files[i], LANDLOCK_ACCESS_FS_READ_FILE, 1)) failed = -1;
    /* Device nodes are deliberately not covered by the root-file ownership
     * check above: PrivateDevices supplies these kernel-created public nodes. */
    int nullfd = open("/dev/null", O_PATH | O_CLOEXEC);
    if (nullfd < 0) failed = -1;
    else {
        struct landlock_path_beneath_attr null_rule = {
            .allowed_access = LANDLOCK_ACCESS_FS_READ_FILE | LANDLOCK_ACCESS_FS_WRITE_FILE,
            .parent_fd = nullfd };
        if (syscall(SYS_landlock_add_rule, rules, LANDLOCK_RULE_PATH_BENEATH, &null_rule, 0)) failed = -1;
        close(nullfd);
    }
    /* No rule grants access to procfs, sysfs, data, logs, backups, credentials,
     * temporary files or system configuration directories. Landlock also
     * denies cross-domain process introspection; the separate broker reads
     * the selected exe links without granting proc file access to this reader. */
    if (!failed && syscall(SYS_landlock_restrict_self, rules, 0)) failed = -1;
    close(rules);
    return failed;
}
