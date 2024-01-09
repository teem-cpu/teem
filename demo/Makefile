
# Requires Clang 17+ (for XTHeadCmo)
CLANG ?= clang
RISCV_CLANG ?= $(CLANG) --target=riscv32 -march=rv32im_zicbom_xtheadcmo
CFLAGS ?= -fno-builtin -Os -Wall

.PHONY: all clean

all: $(patsubst %.c,%.s,$(wildcard *.c))

%.s: %.c cpuemu.h
	$(RISCV_CLANG) $(CFLAGS) -S -o $@ $<

clean:
	rm -f *.s
