#include "confinement.h"
#include "broker.h"
#include <unistd.h>

int main(int argc, char **argv) {
    (void)argv;
    if (argc != 1 || getuid() != 0 || geteuid() != 0) return 64;
    if (mrj_start_exe_broker() || mrj_confine()) return 78;
    char *arguments[] = { "@python@", "-I", "-S", "-B", "@collector@", NULL };
    execv(arguments[0], arguments);
    return 78;
}
