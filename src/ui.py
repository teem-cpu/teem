from __future__ import annotations

import os
from math import ceil, floor
from typing import Iterable, Literal, Optional

from .bpu import AbstractBPU, AbstractBTB, AbstractRSB
from .cpu import CPU
from .execution import ExecutionEngine
from .frontend import Frontend
from .instructions import (Instruction, InstrReg, InstrImm, InstrLoadImm, InstrLoad,
                           InstrStore, InstrFlush, InstrFlushAll, InstrCyclecount,
                           InstrBranch, InstrJump, InstrJumpRegister, InstrSerializing,
                           RegID)
from .memory import MemorySubsystem
from .parser import REV_REGISTER_NAMES
from .word import Byte, Word

HEADER = '\033[95m'
BLUE = '\033[94m'
CYAN = '\033[96m'
MAGENTA = '\033[95m'
GREEN = '\033[92m'
RED = '\033[31m'
DARKGREEN = '\033[32m'
DARKBLUE = '\033[34m'
BRIGHTYELLOW = '\033[93m'
WARNING = '\033[93m'
FAIL = '\033[91m'
ENDC = '\033[0m'
BOLD = '\033[1m'
UNDERLINE = '\033[4m'
FAINT = '\033[2m'
ORANGE = '\033[33m'
FAINTYELLOW = '\033[2;93m'

BOX_SOUTHEAST = '╭'
BOX_SOUTHWEST = '╮'
BOX_NORTHEAST = '╰'
BOX_NORTHWEST = '╯'
BOX_HORIZOZTAL = '─'
BOX_VERTICAL = '│'
BOX_CROSS = '┼'
BOX_NES = '├'
BOX_NSW = '┤'
BOX_NEW = '┴'
BOX_ESW = '┬'
BOX_ARROW_FILLED = '►'
BOX_ARROW_OUTLINE = '▻'
BOX_TRIANGLE_MINI = '▸'
BOX_TRIANGLE_FILLED = '▶'
BOX_TRIANGLE_OUTLINE = '▷'
BOX_ARROW_BIG_OUTLINE = "⇨"
BOX_ARROW_PHAT = '🠊'

WORD_HEX_DIGITS = (Word.WIDTH + 3) // 4

TARGET_PROG_LINES = 16

# get terminal size
columns: int = 120
rows: int = 30


def get_terminal_size():
    global columns, rows
    try:
        columns, rows = os.get_terminal_size(0)
    except OSError:
        columns, rows = 120, 30


# print colored text using ANSI escape sequences
def print_color(c, str, newline=False):
    print(fmt_color(c, str, newline=newline), end="")


def fmt_color(c, str, newline=False):
    return c + str + ENDC + ("\n" if newline else "")


# print a simple divider
def print_div(c=None, length=None, newline=True):
    global columns
    str = "-" * (length if length is not None else columns)
    if c is None:
        print(str, end=("\n" if newline else ""))
    else:
        print_color(c, str, newline)


# print a divider with a header
def print_header(str, c=ENDC):
    inlay = "[ " + str + " ]"
    length = (columns - len(inlay)) // 2
    print_div(c, length, False)
    print_color(c, inlay)
    print_div(c, length + (columns - len(inlay)) % 2, True)


def print_hex(num: int, p_end="", base=True,
              base_style=FAINT, style=ENDC) -> None:
    print(
        hex_str(
            num,
            p_end=p_end,
            base=base,
            base_style=base_style,
            style=style),
        end="")


def hex_str(num: int, p_end="", base=True, fixed_width=True,
            base_style=FAINT, style=ENDC) -> str:
    num_str = format(num, "x")
    padding_str = "0" * (WORD_HEX_DIGITS - len(num_str)) if fixed_width else ""
    base_str = "0x" if base else ""
    return base_style + base_str + padding_str + ENDC + style + num_str + ENDC + p_end


def symbol_str(addr: int, sym_index: Optional[dict[int, list[str]]] = None,
               append: str = "") -> tuple[str, int]:
    if sym_index and sym_index.get(addr):
        addr_symbols = sym_index[addr]
        if len(addr_symbols) > 1:
            addr_symbols = [sym for sym in addr_symbols if not sym.startswith(".")]

        text = addr_symbols[0] + append
        return fmt_color(BRIGHTYELLOW, text), len(text)

    else:
        text = '{:x}'.format(addr)
        return FAINTYELLOW + "0x" + ENDC + BRIGHTYELLOW + text + ENDC, 2 + len(text)


def print_memory(memory: MemorySubsystem,
                 start: int = 0x0, end: Optional[int] = None,
                 lines: Optional[int] = 8, hexdump: bool = False):
    if hexdump:
        words_per_line = (columns - WORD_HEX_DIGITS - 8) // (WORD_HEX_DIGITS + Word.WIDTH_BYTES + 2)
    else:
        words_per_line = (columns - WORD_HEX_DIGITS - 4) // (WORD_HEX_DIGITS + 1)

    if words_per_line >= 8:
        words_per_line -= words_per_line % 8
    elif words_per_line >= 4:
        words_per_line = 4

    bytes_per_line = words_per_line * Word.WIDTH_BYTES

    if end is None and lines is None:
        end = start + bytes_per_line * 8
    elif end is None:
        assert lines is not None
        end = start + bytes_per_line * lines
    elif lines is not None:
        end = min(end, start + bytes_per_line * lines)

    i = start
    while i < end and i < memory.mem_size:
        line_start_i = i
        print_hex(i, p_end=": ", base_style=BOLD + BRIGHTYELLOW, style=BOLD + BRIGHTYELLOW)

        for _ in range(words_per_line):
            if i >= memory.mem_size:
                break
            mem_value = memory._get_word(i)
            cached = memory.is_addr_cached(Word(i))
            print_hex(mem_value, p_end=" ", base=False,
                      base_style=(FAINT + RED if cached else FAINT), style=(RED if cached else ''))
            i += Word.WIDTH_BYTES

        if hexdump:
            print(' |', end='')

            for j in range(line_start_i, line_start_i + bytes_per_line):
                if j >= memory.mem_size:
                    break
                if j > line_start_i and (j - line_start_i) % Word.WIDTH_BYTES == 0:
                    print(ENDC + ' ', end='')
                mem_value = memory._get(j)
                char = '.'
                if mem_value == 0:
                    color = RED
                elif mem_value >= 0x7F:
                    color = BLUE
                elif mem_value < 0x20:
                    color = GREEN
                else:
                    color = ENDC
                    char = chr(mem_value)
                print(color + char, end='')

            print(ENDC + '|', end='')

        print()


def reg_str(val) -> str:
    if isinstance(val, Word):
        return hex_str(val.value, base_style=ENDC + FAINT)
    elif isinstance(val, int):
        return ENDC + DARKBLUE + "RS {:<{}}".format(val, WORD_HEX_DIGITS - 1) + ENDC
    else:
        return BOLD + RED + "ERR"


def print_regs(engine: ExecutionEngine, reg_capitalisation: bool = False):
    regs = engine._registers
    fits = (columns + 3) // (10 + WORD_HEX_DIGITS)
    lines = ceil(len(regs) / fits)
    i = 0
    for _ in range(lines):
        for j in range(fits):
            if i >= len(regs):
                break
            print(" " if j != 0 else "", end="")

            reg_name = f'x{i}'
            if i != 0:
                # "zero" is long and breaks the three-column alignment.
                reg_name = REV_REGISTER_NAMES.get(reg_name, reg_name)
            print(BOLD + GREEN + reg_name.ljust(3) + ": ", end="")

            val = regs[i]
            print(reg_str(val), end="")
            print(" │" if j != fits - 1 else "\n", end="")
            i += 1
    print()


def print_cache(mem: MemorySubsystem, show_empty_sets: bool, show_empty_ways: bool) -> None:
    # long_index = True if num_index_bits > 12 else False
    # long_tag = True if num_tag_bits > 12 else False
    def format_index(idx):
        return f"{FAINT}0x{ENDC}{idx:03x}"

    def format_tag(tag):
        return f"{FAINT}0x{ENDC}{'{:0{}x}'.format(tag, tag_length - 2)}"

    tag_length = 2 + WORD_HEX_DIGITS
    data_length = 1 + (3 + WORD_HEX_DIGITS) * (mem.cache.line_size // Word.WIDTH_BYTES)

    data_header = ('─' * floor((data_length - 4) / 2)) + "Data" + ('─' * ceil((data_length - 4) / 2))
    print(f"╭─Index─┬─{'Tag'.center(tag_length, '─')}─┬{data_header}╮")

    for i, set in enumerate(mem.cache.sets):

        if len([entry for entry in set if entry.is_in_use()]) == 0 and show_empty_sets is False:
            print(f"├─{'─' * 5}─┼─{'─' * tag_length}─┼{'─' * data_length}┤")
            print(f"│ {format_index(i)} │ {'empty'.center(tag_length)} │{' ' * (data_length)}│")
            continue

        if i != 0:
            print(f"├─{'─' * 5}─┼─{'─' * tag_length}─┼{'─' * data_length}┤")

        if show_empty_ways is False:
            set = [entry for entry in set if entry.is_in_use()]

        for j, entry in enumerate(set):

            if (j + 1) == ceil(len(set) / 2) and len(set) % 2 == 1:
                index_gap = format_index(i)
            else:
                index_gap = ' ' * 5

            if entry.is_in_use():
                print(f"│ {index_gap} │ {format_tag(entry.tag)} │ ", end="")
                for word in Word.from_bytes_list([Byte(b) for b in entry.data]):
                    print(f"{hex_str(word.value, p_end=' ')}", end='')
                print("│")
            else:
                print(f"│ {index_gap} │ {' ' * tag_length} │{' ' * data_length}│")

            if (j + 1) == ceil(len(set) / 2) and len(set) % 2 == 0:
                index_gap = format_index(i)
            else:
                index_gap = ' ' * 5

            if j != len(set) - 1:
                print(f"│ {index_gap} ├─{'─' * tag_length}─┼{'─' * data_length}┤")

    print(f"╰─{'─' * 5}─┴─{'─' * tag_length}─┴{'─' * data_length}╯")


def instruction_str(instr: Instruction, reg_capitalisation: bool = False, align_addr: int = 0,
                    pad_type: bool = True, sym_index: Optional[dict[int, list[str]]] = None) -> tuple[str, int]:
    def register_str(reg_id: RegID) -> tuple[str, int]:
        name = f'x{reg_id}'
        if reg_id == 0:
            # Avoid using the long name "zero".
            style = FAINT + DARKGREEN
        else:
            name = REV_REGISTER_NAMES.get(name, name)
            style = DARKGREEN
        if reg_capitalisation:
            name = name.upper()
        return f'{style}{name}{ENDC}', len(name)

    raw_addr_str = format(instr.addr, 'x')
    addr_str = f"{' ' * max(align_addr - len(raw_addr_str), 0)}{FAINT}{raw_addr_str}{ENDC}"
    length = max(len(raw_addr_str), align_addr)

    instr_str = f" {ORANGE}{instr.ty.name}{ENDC}"
    length += 1 + len(instr.ty.name)
    if pad_type:
        padding = max(0, 6 - len(instr.ty.name))
        instr_str += ' ' * padding
        length += padding

    op_str = ""

    if isinstance(instr.ty, (InstrReg, InstrCyclecount)):
        for index, op in enumerate(instr.ops):
            reg_str, reg_len = register_str(RegID(op))
            op_str += " " + reg_str
            length += 1 + reg_len
            if index != len(instr.ops) - 1:
                op_str += ","
                length += 1

    elif isinstance(instr.ty, (InstrStore, InstrLoad, InstrImm, InstrLoadImm, InstrFlush, InstrFlushAll, InstrSerializing)):
        is_memory = isinstance(instr.ty, (InstrStore, InstrLoad))
        for index, op in enumerate(instr.ops):
            if index == len(instr.ops) - 1:
                if is_memory:
                    sym_str, sym_len = symbol_str(Word(op).value)
                else:
                    sym_str = hex_str(Word(op).value, base_style=FAINT, style="", fixed_width=False)
                    sym_len = len(hex(Word(op).value))

                op_str += " " + sym_str
                length += 1 + sym_len
            else:
                reg_str, reg_len = register_str(RegID(op))
                op_str += f" {reg_str},"
                length += 2 + reg_len

    elif isinstance(instr.ty, InstrBranch):
        for index, op in enumerate(instr.ops):
            if index == len(instr.ops) - 1:
                sym_str, sym_len = symbol_str(op, sym_index)
                op_str += " " + sym_str
                length += 1 + sym_len
            else:
                reg_str, reg_len = register_str(RegID(op))
                op_str += f" {reg_str},"
                length += 2 + reg_len

    elif isinstance(instr.ty, (InstrJump, InstrJumpRegister)):
        op_str += " "
        length += 1

        for index, op in enumerate(instr.ops):
            if index > 0:
                op_str += ", "
                length += 2

            op_ty = instr.ty.operand_types[index]
            if op_ty == "reg":
                reg_str, reg_len = register_str(RegID(op))
                op_str += reg_str
                length += reg_len
            elif op_ty == "imm":
                sym_str, sym_len = symbol_str(op)
                op_str += sym_str
                length += sym_len
            elif op_ty == "code_label":
                sym_str, sym_len = symbol_str(op, sym_index)
                op_str += sym_str
                length += sym_len
            else:
                raise RuntimeError(f'Unexpected operand type: {op_ty}')

    else:
        raise RuntimeError(f'Unknown instruction type: {instr.ty}')

    final_str = addr_str + instr_str + op_str

    return final_str, length


def print_queue(queue: Frontend, reg_capitalisation: bool = False):
    q_str, _ = queue_str(queue, reg_capitalisation)
    for line in q_str:
        print(line)


def queue_str(queue: Frontend, reg_capitalisation: bool = False) -> tuple[list[str], list[int]]:
    align_addr = max([len(format(item.instr.addr, 'x')) for item in queue.instr_queue], default=0)
    q_str: list[str] = [""] * len(queue.instr_queue)
    q_lengths: list[int] = [0] * len(queue.instr_queue)
    for index, item in enumerate(queue.instr_queue):
        instr = item.instr
        q_str[index], q_lengths[index] = instruction_str(instr, reg_capitalisation, align_addr=align_addr)
    return q_str, q_lengths


def print_prog(front: Frontend, engine: ExecutionEngine, sym_index: dict[int, list[str]],
               breakpoints: dict[int, bool], focus_instrs: list[int] = [],
               mode: Literal["full", "partial"] = "full", reg_capitalisation: bool = False):
    prog, _ = prog_str(front, engine, sym_index, breakpoints, focus_instrs,
                       wide=True, reg_capitalisation=reg_capitalisation)
    for line in prog:
        print(line)


def select_prog_instrs(front: Frontend, engine: ExecutionEngine, sym_index: dict[int, list[str]],
                       breakpoints: dict[int, bool], focus_instrs: list[int]) -> list[int]:
    def add_addrs(addrs: Iterable[int]) -> None:
        for addr in addrs:
            if addr not in sym_index and addr > front.pc_bounds[0]:
                result_set.add(addr - 4)
            result_set.add(addr)
            if addr < front.pc_bounds[1] - 4:
                result_set.add(addr + 4)

    def update_and_estimate_lines() -> int:
        result[:] = sorted(result_set)
        result_changed = False

        lines = 0
        next_addr = front.pc_bounds[0]
        for addr in result:
            if addr != next_addr:
                if addr == next_addr + 4:
                    # Fill gap where there will be an abbreviation sign anyway.
                    result_set.add(next_addr)
                    result_changed = True
                lines += 1

            if addr in sym_index:
                lines += 1
            lines += 1
            next_addr = addr + 4

        if next_addr != front.pc_bounds[1]:
            if front.pc_bounds[1] == next_addr + 4:
                # See the similar case above.
                result_set.add(next_addr)
                result_changed = True
            lines += 1

        if result_changed:
            result[:] = sorted(result_set)

        return lines

    result: list[int] = []
    result_set: set[int] = set()

    add_addrs(slot.instr.addr for slot in engine.slots() if slot is not None)
    add_addrs(focus_instrs)

    lines = update_and_estimate_lines()
    if lines < TARGET_PROG_LINES:
        add_addrs(item.instr.addr for item in front.instr_queue)

    lines = update_and_estimate_lines()
    if lines < TARGET_PROG_LINES:
        add_addrs(breakpoints)

    lines = update_and_estimate_lines()
    if lines < TARGET_PROG_LINES:
        addr = result[0] + 4 if result else front.pc_bounds[0]
        while addr < front.pc_bounds[1] and update_and_estimate_lines() < TARGET_PROG_LINES:
            result_set.add(addr)
            addr += 4

    update_and_estimate_lines()
    return result


def prog_str(front: Frontend, engine: ExecutionEngine, sym_index: dict[int, list[str]],
             breakpoints: dict[int, bool], focus_instrs: list[int],
             mode: Literal["full", "partial"] = "full",
             wide: bool = False, reg_capitalisation: bool = False) -> tuple[list[str], list[int]]:

    if mode == "full":
        start = front.pc_bounds[0]
        end = front.pc_bounds[1]
        assert (end - start) % 4 == 0
        addresses = list(range(start, end, 4))
    else:
        # Display as many instructions as possible without making the display excessively long.
        addresses = select_prog_instrs(front, engine, sym_index, breakpoints, focus_instrs)
        start, end = addresses[0], addresses[-1] + 4

    lines: list[str] = []
    line_lengths: list[int] = []

    inflights = [slot.instr.addr for slot in engine.slots() if slot is not None]
    queued = [item.instr.addr for item in front.instr_queue]
    active_breakpoints = [pt for pt in breakpoints if breakpoints[pt]]
    disabled_breakpoints = [pt for pt in breakpoints if not breakpoints[pt]]

    align_addr = len(format(max(start, end - 1), 'x'))

    for n, addr in enumerate(addresses):
        # print abbreviation mark
        if n == 0 and addr > front.pc_bounds[0] or addr > addresses[n - 1] + 4:
            lines.append("  " + FAINT + "..." + ENDC)
            line_lengths.append(5)

        # print symbol
        if addr in sym_index:
            cur_line, line_length = symbol_str(addr, sym_index, append=":")
            lines.append(cur_line)
            line_lengths.append(line_length)

        # print status tag
        if addr in inflights and addr in active_breakpoints:
            cur_line = fmt_color(BOLD + RED, BOX_TRIANGLE_FILLED + " ", False)
        elif addr in focus_instrs:
            cur_line = fmt_color(BOLD + BLUE, BOX_TRIANGLE_FILLED + " ", False)
        elif addr in inflights:
            cur_line = fmt_color(BOLD + GREEN, BOX_TRIANGLE_FILLED + " ", False)
        elif addr in active_breakpoints:
            cur_line = fmt_color(BOLD + RED, "◉ ", False)
        elif addr in disabled_breakpoints:
            cur_line = fmt_color(BOLD + RED, "○ ", False)
        elif addr in queued:
            cur_line = fmt_color(FAINT, BOX_TRIANGLE_FILLED + " ", False)
        else:
            cur_line = "  "

        # print instruction
        instr = front.instr_at(addr)
        instr_part, length = instruction_str(instr, reg_capitalisation, align_addr,
                                             sym_index=(sym_index if wide else None))
        cur_line += instr_part

        lines.append(cur_line)
        line_lengths.append(2 + length)

        # print final abbreviation mark
        if n == len(addresses) - 1 and addr + 4 < front.pc_bounds[1]:
            lines.append("  " + FAINT + "..." + ENDC)
            line_lengths.append(5)

    return lines, line_lengths


def print_rs(engine: ExecutionEngine, show_rs_empty: bool, reg_capitalisation: bool = False) -> None:
    strings, _ = rs_str(engine, show_empty=show_rs_empty, reg_capitalisation=reg_capitalisation)
    for line in strings:
        if line != "":
            print(line)


def rs_str(engine: ExecutionEngine, show_empty=True, reg_capitalisation: bool = False) -> tuple[list[str], int]:
    align_addr: int = max([len(format(slot.instr.addr, 'x')) for slot in engine.slots() if slot is not None], default=0)
    max_index_length: int = len(str(len(engine.slots())))

    indices = []
    instructions = []
    status = []
    instr_lengths: list[int] = []

    for i, slot in enumerate(engine.slots()):
        index_str = str(i)
        indices.append(f"{' ' * (max_index_length - len(index_str))}{DARKBLUE}{index_str}{ENDC}")

        if slot is None:
            instructions += [""]
            status += [""]
            instr_lengths += [0]
            continue

        instr_str, instr_length = instruction_str(slot.instr, reg_capitalisation, align_addr)
        instructions.append(instr_str)

        status_str = f"{ORANGE}☐{ENDC}" if slot.executing else f"{GREEN}☑{ENDC}"
        status.append(status_str)

        instr_lengths.append(instr_length)

    max_instr_length = max(max(instr_lengths, default=0), 10)
    max_value_length = 2 + WORD_HEX_DIGITS

    rs_length: int = max_index_length + max_instr_length + 2 * max_value_length + 17

    rs_str: list[str] = []

    line_top = '╭' + '─' * (max_index_length + 2) + '┬' + '─' * (max_instr_length + 2)
    line_top += ('┬──' + '─' * max_value_length) * 2 + '┬───╮'
    assert len(line_top) == rs_length
    rs_str.append(line_top)

    for i, slot in enumerate(engine.slots()):
        if slot is None:
            if show_empty:
                line = '│ ' + indices[i] + ' │ ' + ' ' * max_instr_length
                line += (' │ ' + ' ' * max_value_length) * 2 + ' │   │'
                rs_str.append(line)
            continue
        else:
            line = '│ ' + indices[i] + ' │ '
            line += instructions[i] + ' ' * (max_instr_length - instr_lengths[i]) + ' │'
            line += f" {reg_str(slot.source_operands[0]) if len(slot.source_operands) >= 1 else ' ' * max_value_length} │"
            line += f" {reg_str(slot.source_operands[1]) if len(slot.source_operands) >= 2 else ' ' * max_value_length} │"
            line += f" {status[i]} │"
            rs_str.append(line)

    line_bot = '╰' + '─' * (max_index_length + 2) + '┴'
    line_bot += '─' * (max_instr_length + 2)
    line_bot += ('┴──' + '─' * max_value_length) * 2 + '┴───╯'
    assert len(line_bot) == rs_length
    rs_str.append(line_bot)

    return rs_str, rs_length


def print_bpu(bpu: AbstractBPU) -> None:
    print(bpu, end="")


def print_btb(btb: AbstractBTB) -> None:
    print(btb, end="")


def print_rsb(rsb: AbstractRSB) -> None:
    print(rsb, end="")


def print_info(cpu: CPU) -> None:
    print("PC: ", cpu.get_frontend_or_fail().get_pc(), end="")


def header_memory(memory: MemorySubsystem):
    print_header("Memory", BOLD + BRIGHTYELLOW)
    print()
    print_memory(memory)
    print()


def header_regs(engine: ExecutionEngine, reg_capitalisation: bool = False):
    print_header("Registers", BOLD + GREEN)
    print()
    print_regs(engine, reg_capitalisation)
    print()


def header_pipeline(front: Frontend, engine: ExecutionEngine, sym_index: dict[int, list[str]],
                    breakpoints: dict[int, bool], focus_instrs: list[int],
                    show_rs_empty: bool = True, reg_capitalisation: bool = False):
    prog, prog_lengths = prog_str(front, engine, sym_index, breakpoints, focus_instrs,
                                  mode="partial", reg_capitalisation=reg_capitalisation)
    arrow = ["  ╭─► "] + ["  │   "] * (len(prog) - 2) + [" ─╯   "]
    q, q_lengths = queue_str(front, reg_capitalisation=reg_capitalisation)
    rs, rs_length = rs_str(engine, show_empty=show_rs_empty, reg_capitalisation=reg_capitalisation)

    lines = max(len(prog), len(q), len(rs) - 1)

    max_prog = max(prog_lengths) if prog_lengths else 25
    max_arrow = 6
    max_q = max(q_lengths) if q_lengths else 25

    prog = [prog[i] + " " * (max_prog - prog_lengths[i])
            for i in range(len(prog))] + [" " * max_prog] * (lines - len(prog))
    arrow = arrow + [" " * max_arrow] * (lines - len(arrow))
    q = [q[i] + " " * (max_q - q_lengths[i])
         for i in range(len(q))] + [" " * max_q] * (lines - len(q))

    header_str = "-" * ceil((max_prog - len("[ Program ]")) / 2) + "[ Program ]" + "-" * floor((max_prog - len("[ Program ]")) / 2)
    header_str += "-" * max_arrow
    header_str += "-" * ceil((max_q - len("[ Queue ]")) / 2) + "[ Queue ]" + "-" * floor((max_q - len("[ Queue ]")) / 2)
    header_str += "-" * 4
    header_str += "-" * ceil((rs_length - len("[ Reservation Stations ]")) / 2) + "[ Reservation Stations ]" + "-" * floor((rs_length - len("[ Reservation Stations ]")) / 2)

    if columns < len(header_str):
        print_header("Program", BOLD + CYAN)
        print_prog(front, engine, sym_index, breakpoints, focus_instrs, mode="partial", reg_capitalisation=reg_capitalisation)
        print_header("Queue", BOLD + CYAN)
        print_queue(front)
        print_header("Reservation Stations", BOLD + CYAN)
        print_rs(engine, show_rs_empty=show_rs_empty)
        print(BOLD + RED + UNDERLINE + "Please increase the terminal width to at least " + str(len(header_str)) + " characters" + ENDC + "\n")
        return
    print(BOLD + CYAN + header_str + "-" * (columns - len(header_str)) + ENDC)

    print(" " * (max_prog + max_arrow + max_q + 4), end="")
    print(rs[0])

    for i in range(max(len(prog), len(q), len(rs))):
        if i < len(prog):
            print(prog[i], end="")
            print(arrow[i], end="") if len(front.instr_queue) else print(" " * max_arrow, end="")
        if i < len(q):
            print(q[i], end="")
        print("    ", end="") if i != 0 or len(front.instr_queue) == 0 else print(" " + "─►" + " ", end="")
        if i < len(rs) - 1:
            print(rs[i + 1], end="")
        print("")
    print()


def header_info(cpu: CPU):
    print_header("Info", BOLD + CYAN)
    print()
    print_info(cpu)
    print()


def header_rs(engine: ExecutionEngine, show_rs_empty: bool = True, reg_capitalisation: bool = False):
    print_header("Reservation Stations", BOLD + CYAN)
    print()
    print_rs(engine, show_rs_empty=show_rs_empty, reg_capitalisation=reg_capitalisation)
    print()


def all_headers(cpu: CPU, breakpoints: dict[int, bool], focus_instrs: list[int] = []):
    header_regs(cpu.get_exec_engine(), cpu._config["UX"]["reg_capitalisation"])
    header_memory(cpu.get_memory_subsystem())
    header_pipeline(cpu.get_frontend_or_fail(), cpu.get_exec_engine(), cpu._symbol_index,
                    breakpoints, focus_instrs,
                    show_rs_empty=cpu._config["UX"]["show_empty_slots"],
                    reg_capitalisation=cpu._config["UX"]["reg_capitalisation"])
