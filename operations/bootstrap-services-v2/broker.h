#ifndef MRJ_BROKER_H
#define MRJ_BROKER_H
#include <stdint.h>
#define MRJ_EXE_FD 3
#define MRJ_EXE_MAX 4096
struct mrj_exe_response { uint32_t code; uint32_t length; char path[MRJ_EXE_MAX]; };
int mrj_restrict_exe_broker(void);
int mrj_start_exe_broker(void);
int mrj_exe_link(uint32_t pid, char *output, unsigned maximum);
#endif
