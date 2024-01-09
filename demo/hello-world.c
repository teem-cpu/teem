
/* Hello World on the CPU emulator in C! */

/* This arranges for main() to be called, and defines the following functions:
 *     void exit(int status);                   -- Halt execution
 *     int write(const char *buffer, int size); -- Write to console
 *     int read(char *buffer, int size);        -- Read from console
 *
 * The following functions wrap single assembly instructions:
 *     void breakpoint(void);  -- Software breakpoint
 *     void fence(void);       -- Serialize program execution
 *     int rdcycle(void);      -- Read cycle counter
 *     void flush(void *addr); -- Flush cache line containing addr
 *     void flushall(void);    -- Flush entire cache
 */
#include "cpuemu.h"

int main(void) {
    write("Hello World!\n", 13);
    return 0;
}
