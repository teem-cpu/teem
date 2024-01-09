
/* cpuemu.h -- Header file for C programs to run on the CPU emulator. */

#ifndef CPUEMU_H
#define CPUEMU_H

/* System call numbers. */
#define _EMUNR_exit  -1
#define _EMUNR_write -2
#define _EMUNR_read  -3

/* Conventional stringification macros. */
#define __STR(x) #x
#define _STR(x) __STR(x)

/* Emit an inline assembly block that calls the given main function.
 * Should appear before any function or data declarations. */
#define _EMU_STARTUP(main_func) asm (                               \
    ".text; "                                                       \
    "_start: "                                                      \
    /* Initialize stack pointer to somewhere far away. */           \
    "li sp, 0x10000000; "                                           \
    /* Call main function (argc and argv are already 0). */         \
    "call " #main_func "; "                                         \
    /* Pass return value to exit system call. */                    \
    "li a7, " _STR(_EMUNR_exit) "; "                                \
    "ecall; "                                                       \
    /* That shouldn't have failed, but handle this case somehow. */ \
    "_HALT: "                                                       \
    "j _HALT"                                                       \
);

/* Define this macro if you supply your own startup code. */
#ifndef EMU_NO_DEFAULT_STARTUP
_EMU_STARTUP(main)
#endif


/* Intrinsic functions for special assembly instructions. */

/* Cause a software breakpoint */
static inline void breakpoint(void) {
    asm volatile ( "ebreak" ::: "memory" );
}

/* Serialize the instruction stream.
 * All instructions before the fence finish before any instructions after the
 * fence are issued. */
static inline void fence(void) {
    asm volatile ( "fence.i" ::: "memory" );
}

/* Read the cycle counter.
 * returns -- Cycle count as of the function's call. */
static inline int rdcycle(void) {
    register int _R_result;
    asm volatile ( "rdcycle %0" : "=r"(_R_result) );
    return _R_result;
}

/* Flush the cache line containing addr.
 * addr -- The address to flush. */
static inline void flush(void *__addr) {
    asm volatile ( "cbo.flush (%0)" :: "r"(__addr) : "memory" );
}

/* Flush the entire cache. */
static inline void flushall(void) {
    asm volatile ( "th.dcache.ciall" ::: "memory" );
}


/* Internal convenience macros for system calls.
 * Must be used together with register-bound variables to work correctly. */
#define _EMU_SYSCALL(rv, no, ...) asm volatile (                \
    "li a7, " #no "; ecall" : "=r"(rv) : __VA_ARGS__ : "memory" \
)
#define _EMU_SYSCALL0(rv, no)             \
    _EMU_SYSCALL(rv, no)
#define _EMU_SYSCALL1(rv, no, a1)         \
    _EMU_SYSCALL(rv, no, "r"(a1))
#define _EMU_SYSCALL2(rv, no, a1, a2)     \
    _EMU_SYSCALL(rv, no, "r"(a1), "r"(a2))


/* System call wrappers. */

/* Shut down the emulator.
 * status  -- The exit status as an integer.
 * returns -- Never. */
static inline void exit(int __status) {
    register int _R_status asm("a0") = __status;
    register int _R_result asm("a0");
    _EMU_SYSCALL1(_R_result, _EMUNR_exit, _R_status);
}

/* Write from buffer to console.
 * buffer  -- Buffer to write from. Must be at least size bytes long.
 * size    -- Amount of bytes to write.
 * returns -- Amount of bytes written (always equal to size). */
static inline int write(const void *__buffer, int __size) {
    register int _R_buffer asm("a0") = (int) __buffer;
    register int _R_size   asm("a1") =       __size;
    register int _R_result asm("a0");
    _EMU_SYSCALL2(_R_result, _EMUNR_write, _R_buffer, _R_size);
    return _R_result;
}

/* Read from console into buffer.
 * buffer  -- Buffer to store into. Must have at least size bytes' space.
 * size    -- Maximum amount to read at once. If more bytes are available for
 *            reading, they are buffered internally until the next read()
 *            call.
 * returns -- Amount of bytes read.
 */
static inline int read(void *__buffer, int __size) {
    register int _R_buffer asm("a0") = (int) __buffer;
    register int _R_size   asm("a1") =       __size;
    register int _R_result asm("a0");
    _EMU_SYSCALL2(_R_result, _EMUNR_read, _R_buffer, _R_size);
    return _R_result;
}

#endif
