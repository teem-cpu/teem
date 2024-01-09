# CPU emulator instruction set

The CPU emulator implements most of the `RV32IM` RISC-V instruction set as defined by the
[RISC-V ISA specification][1], as well as a few instructions (mis)appropriated from assorted extensions.

This document summarizes the instructions implemented by the emulator. The meaning of most instructions is stated by
giving equivalent C code snippets.

The emulator's most significant deviation from the RISC-V ISA is that it does not constrain the range of immediate
operands. Assembly source texts that use positive literals for sign-extended immediates (such as `4095` instead of
`-1`) will be interpreted incorrectly.

## Instruction table syntax

In the following, `rd`, `rs1`, `rs2`, `rv`, `rm` are general-purpose registers (`x0` through `x31`).
The syntax `off(rm)` denotes memory starting at the address `rm + off`. Either of `off` or `(rm)` (but not both) may
be omitted. `off` may be a fixed integer or a label.
`label` denotes a label in the assembly source text. For some instructions, the assembler requires the label to lie
in the `.text` section as a sanity check.

In C code, `iN`/`uN` are signed/unsigned `N`-bit two's-complement integer types. Where the signedness of a value is
relevant, it is explicitly cast to an `iN` or `uN` type.

## Register names

All RISC-V registers have at least two names, one systematic name and one name related to the register's role in the
standard calling convention. The below table gives the relations between the various registers.

| Reg         | Name       | Expansion      | Note                                                    |
| ----------- | ---------- | -------------- | ------------------------------------------------------- |
| `x0`        | `zero`     | Zero register  | Always reads as zero; discards all writes               |
| `x1`        | `ra`       | Return address | Used by default by some jump instructions               |
| `x2`        | `sp`       | Stack pointer  | By convention                                           |
| `x3`        | `gp`       | Global pointer | May be used to efficiently address globals              |
| `x4`        | `tp`       | Thread pointer | May be used to efficiently address thread-local storage |
| `x5`–`x7`   | `t0`–`t2`  | Temporary      | Scratch registers                                       |
| `x8`–`x9`   | `s0`–`s1`  | Saved          | `s0` is also the stack frame pointer `fp`               |
| `x10`–`x17` | `a0`–`a7`  | Argument       | `a0` and `a1` are also used for return values           |
| `x18`–`x27` | `s2`–`s11` | Saved          |                                                         |
| `x28`–`x31` | `t3`–`t6`  | Temporary      | Scratch registers                                       |

The stack pointer `sp` and all `s*` registers are callee-saved: If a function modifies a `s*` register, it must save
its original value on the stack and restore it before returning.
The pointers `gp` and `tp` should not be modified by any (non-system) function.
All other registers may be used freely.

## Arithmetic instructions

| Instruction        | C code                  |
| ------------------ | ----------------------- |
| `ADD rd, rs1, rs2` | `rd = rs1 + rs2`        |
| `SUB rd, rs1, rs2` | `rd = rs1 - rs2`        |
| `SLL rd, rs1, rs2` | `rd = rs1 << rs2`       |
| `SRL rd, rs1, rs2` | `rd = (u32) rs1 >> rs2` |
| `SRA rd, rs1, rs2` | `rd = (i32) rs1 >> rs2` |
| `XOR rd, rs1, rs2` | `rd = rs1 ^ rs2`        |
| `OR  rd, rs1, rs2` | `rd = rs1 \| rs2`       |
| `AND rd, rs1, rs2` | `rd = rs1 & rs2`        |

The logical right shift shifts in zero bits. The arithmetic right shift shifts in copies of the sign bit.

For all of these, `*I rd, rs1, imm` variants are available that use an immediate operand instead of `rs2`. The CPU
emulator does not constrain the immediate operand to any range (but that of 32-bit integers). For example,
`ADDI x5, x5, 1` increments `x5` by `1`.

### Conditional setting instructions

| Instruction          | C code                        |
| -------------------- | ----------------------------- |
| `SLT   rd, rs1, rs2` | `rd = (i32) rs1 <  (i32) rs2` |
| `SLTI  rd, rs1, imm` | `rd = (i32) rs1 <  (i32) imm` |
| `SLTU  rd, rs1, rs2` | `rd = (u32) rs1 <  (u32) rs2` |
| `SLTIU rd, rs1, imm` | `rd = (u32) rs1 <  (u32) imm` |
| `SEQZ  rd, rs1`      | `rd =       rs1 == 0`         |
| `SNEZ  rd, rs1`      | `rd =       rs1 != 0`         |
| `SLTZ  rd, rs1`      | `rd = (i32) rs1 <  0`         |
| `SGTZ  rd, rs1`      | `rd = (i32) rs1 >  0`         |

All of these set `rd` to `1` if the condition is true and to `0` if the condition is false.

### Additional arithmetic instructions

All of these can be synthesized from the other arithmetic instructions, but are provided for convenience.

| Instruction   | C code      | Same as              |
| ------------- | ----------- | -------------------- |
| `LI rd, imm`  | `rd = imm`  | `ADDI rd, zero, imm` |
| `MV rd, rs1`  | `rd = rs1`  | `ADDI rd, rs1, 0`    |
| `NOT rd, rs1` | `rd = ~rs1` | `XORI rd, rs1, -1`   |
| `NEG rd, rs1` | `rd = -rs1` | `SUB rd, zero, rs1`  |

An “actual” RISC-V would translate `LI` instructions with large immediate operands to `LUI`+`ADDI` pairs.

### Special immediate instructions

| Instruction     | C code                  |
| --------------- | ----------------------- |
| `LUI   rd, imm` | `rd =  imm << 12`       |
| `AUIPC rd, imm` | `rd = (imm << 12) + pc` |

`pc` is the instruction's address.

### Multiplication/division (`M` extension)

| Instruction           | C code                                           |
| --------------------- | ------------------------------------------------ |
| `MUL    rd, rs1, rs2` | `rd = rs1 * rs2`                                 |
| `MULH   rd, rs1, rs2` | `rd = ((i64) (i32) rs1 * (i64) (i32) rs2) >> 32` |
| `MULHU  rd, rs1, rs2` | `rd = ((u64) (u32) rs1 * (u64) (u32) rs2) >> 32` |
| `MULHSU rd, rs1, rs2` | `rd = ((u64) (i32) rs1 * (u64) (u32) rs2) >> 32` |
| `DIV    rd, rs1, rs2` | `rd = (i32) rs1 / (i32) rs2`                     |
| `DIVU   rd, rs1, rs2` | `rd = (u32) rs1 / (u32) rs2`                     |
| `REM    rd, rs1, rs2` | `rd = (i32) rs1 % (i32) rs2`                     |
| `REMU   rd, rs1, rs2` | `rd = (u32) rs1 % (u32) rs2`                     |

`MUL` works the same regardless of the signedness of the operands.
`MULH` sign-extends both operands and outputs the upper word of the product.
`MULHU` zero-extends both operands instead.
`MULHSU` sign-extends the first operand and zero-extends the second operand instead.

Division and remainder never cause exceptions, and instead produce particular values:
Dividing by zero produces a quotient of `-1` (the all-ones value for `DIVU`) and a remainder of `rs1`.
A signed division of the most negative value `-1 << 31` by `-1` produces `rs1` as the quotient and `0` as the
remainder.

## Memory access instructions

| Instruction       | C code                   |
| ----------------- | ------------------------ |
| `LW  rv, off(rm)` | `rv = *(i32*)(rm + off)` |
| `LH  rv, off(rm)` | `rv = *(i16*)(rm + off)` |
| `LHU rv, off(rm)` | `rv = *(u16*)(rm + off)` |
| `LB  rv, off(rm)` | `rv = *(i8 *)(rm + off)` |
| `LBU rv, off(rm)` | `rv = *(u8 *)(rm + off)` |
| `SW  rv, off(rm)` | `*(i32*)(rm + off) = rv` |
| `SH  rv, off(rm)` | `*(i16*)(rm + off) = rv` |
| `SB  rv, off(rm)` | `*(i8 *)(rm + off) = rv` |

Loads of values smaller than a word can be sign- or zero-extended.
Stores always truncate away the most significant bits.

The CPU emulator permits unaligned memory accesses. There is no performance penalty.

## Control transfer instructions

### Conditional branches

| Instruction            | C code                                    |
| ---------------------- | ----------------------------------------- |
| `BEQ  rs1, rs2, label` | `if (      rs1 ==       rs2) goto label;` |
| `BNE  rs1, rs2, label` | `if (      rs1 !=       rs2) goto label;` |
| `BLT  rs1, rs2, label` | `if ((i32) rs1 <  (i32) rs2) goto label;` |
| `BLE  rs1, rs2, label` | `if ((i32) rs1 <= (i32) rs2) goto label;` |
| `BGT  rs1, rs2, label` | `if ((i32) rs1 >  (i32) rs2) goto label;` |
| `BGE  rs1, rs2, label` | `if ((i32) rs1 >= (i32) rs2) goto label;` |
| `BLTU rs1, rs2, label` | `if ((u32) rs1 <  (u32) rs2) goto label;` |
| `BLEU rs1, rs2, label` | `if ((u32) rs1 <= (u32) rs2) goto label;` |
| `BGTU rs1, rs2, label` | `if ((u32) rs1 >  (u32) rs2) goto label;` |
| `BGEU rs1, rs2, label` | `if ((u32) rs1 >= (u32) rs2) goto label;` |

For all of these, `B*Z rs1, label` aliases are available that compare `rs1` with the `zero` register.

### Unconditional jumps

| Instruction        | Meaning                                             |
| ------------------ | --------------------------------------------------- |
| `J    label`       | Go to `label`                                       |
| `JR   off(rm)`     | Go to `rm + off`                                    |
| `JAL  rd, label`   | Store return address into `rd` and go to `label`    |
| `JALR rd, off(rm)` | Store return address into `rd` and go to `rm + off` |
| `CALL label`       | Same as `JAL ra, label`                             |
| `TAIL label`       | Same as `JAL zero, label`                           |
| `RET`              | Same as `JALR zero, (ra)`                           |

The “return address” is the address of the following instruction.

The RISC-V specification defines `CALL` and `TAIL` to be two-instruction sequences, but permits tooling to collapse
them into single instructions if the offset is in range. To the CPU emulator, the offset is always in range.

## Special instructions

| Instruction  | Meaning                                               |
| ------------ | ----------------------------------------------------- |
| `RDCYCLE rd` | Set `rd` to the current value of the cycle counter    |
| `FENCE.I`    | Serialize instruction stream                          |
| `ECALL`      | Serialize instruction stream; invoke system call      |
| `EBREAK`     | Serialize instruction stream; force a breakpoint stop |

`RDCYCLE` reads the cycle counter when it is executed.

Instructions that “serialize the instruction stream” suppress fetching, decoding, and executing of any subsequent
instructions until they retire.

### Cache management

| Instruction      | Meaning                                          |
| ---------------- | ------------------------------------------------ |
| `CBO.FLUSH (rm)` | Flush the cache line containing the address `rm` |
| `X.FLUSHALL`     | Flush the entire data cache                      |

Contrary to the `Zicbom` extension, the emulator also permits `CBO.FLUSH` with a nonzero offset, and acts on
`rm + off` in that case.

`X.FLUSHALL` is also available as `TH.DCACHE.CIALL` for Clang compatibility.


[1]: https://github.com/riscv/riscv-isa-manual/releases/download/Ratified-IMAFDQC/riscv-spec-20191213.pdf
