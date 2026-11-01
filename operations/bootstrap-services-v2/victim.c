/* Disposable VM only. No part of this executable enters the production output. */
#include <inttypes.h>
#include <stdio.h>
#include <string.h>
#include <sys/prctl.h>
#include <unistd.h>

static char sentinel[] = "SYNTHETIC_MEMORY_ONLY";
int main(int argc, char **argv) {
    /* Same-UID proc controls must remain accessible after dropping reader
     * capabilities, independently of Yama. This is synthetic fixture setup. */
    if (prctl(PR_SET_PTRACER, PR_SET_PTRACER_ANY, 0, 0, 0)) return 1;
    const char *path = argc == 3 && strcmp(argv[1], "root") == 0
        ? "/run/services-v2-synthetic-root/metadata" : "/run/services-v2-synthetic-victim/metadata";
    FILE *output = fopen(path, "w");
    if (!output) return 1;
    if (fprintf(output, "%ld %" PRIuPTR "\n", (long)getpid(), (uintptr_t)sentinel) < 0) return 1;
    if (fclose(output)) return 1;
    for (;;) pause();
}
