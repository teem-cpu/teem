# CPU emulator assembly language

The CPU emulator interprets a stripped-down subset of RISC-V assembly.

We expect the emulator to accept assembly code produced by `clang -S` without requiring any changes. If you discover a
situation where that does not happen, you are encouraged to raise an issue (or even submit a patch).

This document gives an overview of RISC-V assembly syntax as understood by the emulator.
See [isa.md](isa.md) for a list of the supported instructions.

## Assembly language

Comments are introduced by either of `#` or `//`. Blank lines and lines containing only comments are ignored.

All other lines contain either CPU instructions or assembler directives. Each such line starts with an optional label,
which is identified by the colon (`:`) that follows it. Labels may contain alphanumeric ASCII characters or the
special characters `_.$`.

After the label, a single word identifies the line's CPU instruction or assembler directive. If the word starts with a
dot (`.`), it is an assembler directive; otherwise, it is an instruction.

The instruction/directive is followed by a comma-separated list of arguments. Each argument may be:
- A constant integer (like `0` or `-1`);
- The name of a label;
- (CPU instructions:) A register name (like `x5` or `t0`);
- (CPU instructions:) A memory reference (like `4(s0)`; see [isa.md](isa.md) for details);
- (Directives:) A string enclosed in double quotes, or a string without quotes.

Arithmetic expressions are *not* supported.

## Assembler directives

The CPU emulator supports the following assembler directives. All directives that output data into the current section
are only valid in the `.data` section.

| Syntax                      | Meaning                                                                           |
| --------------------------- | --------------------------------------------------------------------------------- |
| `.text`                     | Switch to the `.text` section.                                                    |
| `.data`                     | Switch to the `.data` section.                                                    |
| `.bss`                      | Switch to the `.bss` section (which is the same as the `.data` section).          |
| `.section NAME`             | Switch to the given section.                                                      |
| `.asciz   STR, ...`         | Output the given strings into the current section, each followed by a zero byte.  |
| `.ascii   STR, ...`         | Same as `.asciz`, but without null termination.                                   |
| `.byte    N, ...`           | Output the byte(s) given as integers into the current section.                    |
| `.short   N, ...`           | Output the 16-bit number(s) given as integers into the current section.           |
| `.long    N, ...`           | Output the 32-bit number(s) given as integers into the current section.           |
| `.quad    N, ...`           | Output the 64-bit number(s) given as integers into the current section.           |
| `.zero    N`                | Output `N` zero bytes into the current section.                                   |
| `.p2align N`                | Ensure the current end of the current section is aligned to a multiple of `2**N`. |
| `.balign  N`                | Ensure the current end of the current section is aligned to a multiple of `N`.    |
| `.comm    SYM, SIZE, ALIGN` | Same as `.align ALIGN` followed by `SYM: .zero SIZE`, all in the `.data` section. |

Some of the directives have alternative names:

| Name     | Also known as      |
| -------- | ------------------ |
| `.asciz` | `.string`          |
| `.short` | `.half`, `.2byte`  |
| `.long`  | `.word`, `.4byte`  |
| `.quad`  | `.dword`, `.8byte` |

These directives are summarily ignored for compatibility with compiler output: `.file`, `.globl`, `.weak`, `.local`,
`.ident`, `.type`, `.size`, `.attribute` as well as `.addrsig` and `.addrsig_sym`.

Any unrecognized directive causes an error.
