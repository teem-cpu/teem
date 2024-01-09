from __future__ import annotations

from prompt_toolkit.completion import NestedCompleter
from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit import __version__ as prompt_toolkit_version
from benedict import __version__ as benedict_version
from os import system
import re
import sys
from benedict import benedict
from collections import deque
import platform
import subprocess
from typing import Optional


from .word import Word
from .byte import Byte
from . import ui
from .cpu import CPU, CPUStatus
from .parser import Parser

PROMPT = ui.BOX_ARROW_FILLED + " "

CATCH_EVENTS = ['branch', 'memory', 'jump', 'ecall', 'ebreak']

session: PromptSession = PromptSession()


funcs = {}
completions = {}
breakpoints: dict[int, bool] = {}


def print_version():
    if platform.system() == 'Windows':
        print(f"Windows {platform.release()}")
    if platform.system() == 'Linux':
        f = open("/etc/os-release", "r")
        lines = f.readlines()
        f.close()
        for i in lines:
            if i.startswith("PRETTY_NAME"):
                print(i.split("\"")[1].strip(), end=" ")
            if i.startswith("BUILD_ID"):
                print(i.split("=")[1].strip(), end="")
        print()
    print(f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
    print(f"Python-Prompt {prompt_toolkit_version}")
    print(f"Python-Benedict {benedict_version}")
    # print(f"https://git.cs.uni-bonn.de/boes/lab_transient_ws_2122/-/tree/{subprocess.check_output(['git', 'rev-parse', 'HEAD']).decode('ascii').strip()}")
    try:
        print(f"Git Commit {subprocess.check_output(['git', 'rev-parse', 'HEAD']).decode('ascii').strip()}")
    except FileNotFoundError:
        print("Git not installed")


def func(f):
    if len(f.__name__[2:]) > 0:
        completions[f.__name__[2:]] = None
        if f.__doc__ is not None:
            completions[f.__name__[2:]] = eval(f.__doc__.strip())
    funcs[f.__name__] = f
    return f


def func_alias(name: str, f):
    funcs["__" + name] = f
    completions[name] = completions[f.__name__[2:]]


def __not_found(input: list[str], cpu: CPU):
    print('Your input did not match any known command')


@func
def __status(input: list[str], cpu: CPU):
    if len(input) != 0:
        __not_found(input, cpu)
        return cpu
    ui.all_headers(cpu, breakpoints)


@func
def __show(input: list[str], cpu: CPU):
    '''
    {"mem": None, "hexmem": None, "cache": None, "regs": None, "queue": None, "rs": None, "prog": None, "bpu": None}
    '''
    if len(input) < 1:
        __not_found(input, cpu)
        return cpu
    subcmd = input[0]
    if subcmd in ('mem', 'hexmem'):
        start: int = 0
        end: Optional[int] = None
        if len(input) == 2:
            # check if the input is an int
            try:
                start = int(input[1], 16)
            except ValueError:
                print("Usage: show mem <start in hex> <words in hex>")
                return cpu
        elif len(input) == 3:
            # check if both inputs are ints
            try:
                start = int(input[1], 16)
                end = start + int(input[2], 16)
            except ValueError:
                print("Usage: show mem <start in hex> <words in hex>")
                return cpu
        else:
            ui.print_memory(cpu.get_memory_subsystem(), hexdump=(subcmd == 'hexmem'))
            return cpu
        start = max(start, 0)
        ui.print_memory(cpu.get_memory_subsystem(), start=start, end=end, lines=None, hexdump=(subcmd == 'hexmem'))
    elif subcmd == 'cache':
        ui.print_cache(cpu.get_memory_subsystem(), cpu._config["UX"]["show_empty_sets"], cpu._config["UX"]["show_empty_ways"])
    elif subcmd == 'regs':
        ui.print_regs(cpu.get_exec_engine(), reg_capitalisation=cpu._config["UX"]["reg_capitalisation"])
    elif subcmd == 'queue':
        ui.print_queue(cpu.get_frontend_or_fail(), reg_capitalisation=cpu._config["UX"]["reg_capitalisation"])
    elif subcmd == 'rs':
        ui.print_rs(cpu.get_exec_engine(), cpu._config["UX"]["show_empty_slots"], reg_capitalisation=cpu._config["UX"]["reg_capitalisation"])
    elif subcmd == 'prog':
        ui.print_prog(cpu.get_frontend_or_fail(), cpu.get_exec_engine(), cpu._symbol_index, breakpoints, reg_capitalisation=cpu._config["UX"]["reg_capitalisation"])
    elif subcmd == 'bpu':
        ui.print_bpu(cpu.get_bpu())
    elif subcmd == 'btb':
        ui.print_btb(cpu.get_btb())
    elif subcmd == 'rsb':
        ui.print_rsb(cpu.get_rsb())
    else:
        __not_found(input, cpu)


@func
def __edit(input: list[str], cpu: CPU) -> CPU:
    '''
    {"word": None, "byte": None, "flush": None, "load": None, "reg": None, "bpu": None}
    '''
    if len(input) < 1:
        __not_found(input, cpu)
        return cpu
    subcmd = input[0]
    if subcmd == 'word':
        if len(input) == 3:
            try:
                addr = int(input[1], base=16)
                val = int(input[2], base=16)
                cpu.get_memory_subsystem().write_word(Word(addr), Word(val), cache_side_effects=False)
            except ValueError:
                print("Usage: edit word <address in hex> <value in hex>")
                return cpu
        else:
            print("Usage: edit word <address in hex> <value in hex>")
    elif subcmd == 'byte':
        if len(input) == 3:
            try:
                addr = int(input[1], base=16)
                val = int(input[2], base=16)
                cpu.get_memory_subsystem().write_byte(Word(addr), Byte(val), cache_side_effects=False)
            except ValueError:
                print("Usage: edit byte <address in hex> <value in hex>")
                return cpu
        else:
            print("Usage: edit word <address in hex> <value in hex>")
    elif subcmd == 'flush':
        if len(input) == 1:
            cpu.get_memory_subsystem().flush_all()
        elif len(input) == 2:
            try:
                addr = int(input[1], base=16)
                cpu.get_memory_subsystem().flush_line(Word(addr))
            except ValueError:
                print("Usage: edit flush <address in hex>")
                return cpu
        else:
            print("Usage: edit flush <address in hex>")
    elif subcmd == 'load':
        if len(input) == 2:
            try:
                addr = int(input[1], base=16)
                cpu.get_memory_subsystem()._load_line(Word(addr))
            except ValueError:
                print("Usage: edit load <address in hex>")
                return cpu
        else:
            print("Usage: edit load <address in hex>")
    elif subcmd == 'reg':
        if len(input) == 3:
            try:
                reg = Parser.parse_register(input[1])
                val = int(input[2], 0)
                if reg is None:
                    print("No such register!")
                    return cpu
                elif reg == 0:
                    print("Discarding write to zero register")
                    return cpu
                cpu.get_exec_engine()._registers[reg] = Word(val)
            except ValueError:
                print("Usage: edit reg <register> <value in hex>")
                return cpu
        else:
            print("Usage: edit reg <register> <value in hex>")
    elif subcmd == 'bpu':
        if len(input) == 3:
            try:
                pc = int(input[1], 16)
                val = int(input[2])
                if val < 0 or val > 3:
                    print("Usage: edit bpu <pc in hex> <value (0-3)>")
                    return cpu
                cpu.get_bpu().set_counter(pc, val)
            except ValueError:
                print("Usage: edit bpu <pc in hex> <value (0-3)>")
                return cpu
        else:
            print("Usage: edit bpu <pc in hex> <value in hex>")
    else:
        __not_found(input, cpu)
    return cpu


@func
def __continue(input: list[str], cpu: CPU) -> CPU:
    return exec(cpu)


func_alias("c", __continue)


@func
def __step(input: list[str], cpu: CPU):
    steps = 1
    info: CPUStatus
    if len(input) == 1:
        try:
            steps = int(input[0])
        except ValueError:
            print("Usage: step <steps>")
            return cpu
        if steps < 0:
            cpu = cpu.restore_snapshot(cpu, steps)
            if cpu is None:
                print("Can't restore snapshot")
                return cpu
            steps = 0
    return exec(cpu, steps)


func_alias("s", __step)

# If we ever gain debugging symbol support, these will become distinct from step.
func_alias("stepi", __step)
func_alias("si", __step)

# Once we gain function call support, these will be distinct from step.
func_alias("next", __step)
func_alias("n", __step)
func_alias("nexti", __step)
func_alias("ni", __step)


@func
def __retire(input: list[str], cpu: CPU) -> CPU:
    return exec(cpu, break_at_retire=True)


def exec(cpu: CPU, steps=-1, break_at_retire=False) -> CPU:
    i: int = 0
    active_breakpoints = [i for i in breakpoints if breakpoints[i] is True]
    while i != steps:
        inflights_before = cpu.get_exec_engine().occupied_slots()
        info: CPUStatus = cpu.tick()

        if info.fault_info is not None:
            show_breakpoints = breakpoints
            if info.fault_info.effect is not None:
                show_breakpoints = breakpoints.copy()
                show_breakpoints[info.fault_info.instr.addr] = True
            ui.all_headers(cpu, show_breakpoints, [info.fault_info.instr.addr])

            break_kind: Optional[str] = None
            if info.fault_info.prediction is not None:
                # branch prediction error
                line = f"{ui.RED + ui.BOLD}Branch prediction error at{ui.ENDC} "
                line += ui.instruction_str(info.fault_info.instr, pad_type=False, sym_index=cpu._symbol_index)[0]
                line += f" {ui.BLUE + ui.BOLD}(predicted branch "
                if info.fault_info.prediction:
                    line += f"{ui.ENDC + ui.DARKGREEN}taken"
                else:
                    line += f"{ui.ENDC + ui.RED}not taken"
                line += f"{ui.ENDC + ui.BLUE + ui.BOLD}){ui.ENDC}"
                print(line)
                break_kind = 'branch'
            elif info.fault_info.address is not None:
                # address error
                line = f"{ui.RED + ui.BOLD}Memory access error at{ui.ENDC} "
                line += ui.instruction_str(info.fault_info.instr, pad_type=False, sym_index=cpu._symbol_index)[0]
                print(line)
                break_kind = 'memory'
            elif info.fault_info.next_instr_addr is not None:
                # mispredicted register jump
                line = f"{ui.RED + ui.BOLD}Jump prediction error at{ui.ENDC} "
                line += ui.instruction_str(info.fault_info.instr, pad_type=False, sym_index=cpu._symbol_index)[0]
                print(line)
                break_kind = 'jump'
            elif info.fault_info.effect is not None:
                # special instruction
                if info.fault_info.effect == 'ebreak':
                    line = f"{ui.RED}SOFTWARE BREAKPOINT at{ui.ENDC} "
                    line += ui.instruction_str(info.fault_info.instr, pad_type=False, sym_index=cpu._symbol_index)[0]
                    print(line)
                    break_kind = 'ebreak'
                elif info.fault_info.effect == 'ecall':
                    line = f"{ui.BLUE + ui.BOLD}System call at{ui.ENDC} "
                    line += ui.instruction_str(info.fault_info.instr, pad_type=False, sym_index=cpu._symbol_index)[0]
                    print(line)
                    break_kind = 'ecall'
                else:
                    print(ui.BOLD + ui.RED + "Unknown special fault" + ui.ENDC)
            else:
                print(ui.BOLD + ui.RED + "Unknown fault" + ui.ENDC)

            if info.fault_microprog is not None:
                print(f"{ui.ORANGE}Microprogram injected: {info.fault_microprog}{ui.ENDC}")
            if (break_kind is None or cpu._config['UX']['BreakAtFault'][break_kind]
                    or cpu._console.need_input):
                return cpu

        if set(active_breakpoints) & set(info.issued_instructions):
            ui.all_headers(cpu, breakpoints)
            ui.print_color(ui.RED, 'BREAKPOINT', newline=True)
            return cpu
        if not info.executing_program:
            ui.all_headers(cpu, breakpoints)
            # Reordering the console output after the "Program finished" message might look confusing.
            handle_console(cpu, flush_output=True)
            line = ui.BLUE + ui.BOLD + "Program finished"
            if cpu._exit_status is None:
                pass
            elif cpu._exit_status == 0:
                line += " with status " + ui.GREEN + "0"
            else:
                line += " with status " + ui.RED + str(cpu._exit_status)
            line += ui.ENDC
            print(line)
            return cpu
        if break_at_retire and len(info.issued_instructions) + cpu.get_exec_engine().occupied_slots() < inflights_before:
            ui.all_headers(cpu, breakpoints)
            ui.print_color(ui.RED, 'RETIRE', newline=True)
            return cpu

        i += 1

    ui.all_headers(cpu, breakpoints)
    return cpu


@func
def __restart(input: list[str], cpu: CPU) -> CPU:
    cpu = cpu.restore_snapshot(cpu, cpu._snapshot_index * -1 + 1)
    ui.all_headers(cpu, breakpoints)
    return cpu


@func
def __break(input: list[str], cpu: CPU):
    '''
    {"add": None, "delete": None, "delete": None, "toggle": None, "list": None}
    '''
    if len(input) < 1:
        __not_found(input, cpu)
        return cpu
    subcmd = input[0]
    if subcmd == 'add':
        if len(input) < 2:
            print("Usage: break add <address in hex>")
            return cpu
        try:
            addr = int(input[1], 16)
            if addr in breakpoints:
                print("Breakpoint already exists")
                return cpu
            breakpoints[addr] = True
            print("Breakpoint added")
        except ValueError:
            print("Usage: break add <address in hex>")
    elif subcmd == 'delete':
        if len(input) < 2:
            print("Usage: break delete <address in hex>")
            return cpu
        try:
            addr = int(input[1], 16)
            if addr not in breakpoints:
                print("Breakpoint does not exist")
                return cpu
            breakpoints.pop(addr)
            print("Breakpoint deleted")
        except ValueError:
            print("Usage: break delete <address in hex>")
    elif subcmd == 'list':
        print("Breakpoints:")
        for addr in breakpoints:
            print(
                "\t{:04x} {}".format(
                    addr,
                    "(disabled)" if not breakpoints[addr] else ""))
    elif subcmd == 'toggle':
        if len(input) < 2:
            print("Usage: break toggle <address in hex>")
            return cpu
        try:
            addr = int(input[1], 16)
            if addr not in breakpoints:
                print("Breakpoint does not exist")
                return cpu
            breakpoints[addr] = not breakpoints[addr]
            print("Breakpoint toogled")
        except ValueError:
            print("Usage: break toogle <address in hex>")
    elif re.match(r'\A[0-9a-fA-F]+\Z', subcmd):
        __break(['add'] + input, cpu)
    else:
        __not_found(input, cpu)


func_alias("b", __break)


@func
def __catch(input: list[str], cpu: CPU):
    if len(input) != 2:
        print("Usage: catch <event> <on|off>")
        return cpu

    mapping = cpu._config['UX']['BreakAtFault']
    event = input[0]
    if event not in mapping:
        print(f"Unknown catch event '{event}', must be one of {', '.join(mapping.keys())}")
        return cpu

    raw_value = input[1].lower()
    if raw_value == 'on':
        value = True
    elif raw_value == 'off':
        value = False
    else:
        print("Usage: catch <event> <on|off>")
        return cpu

    mapping[event] = value
    return cpu


completions['catch'] = {k: {"on": None, "off": None} for k in CATCH_EVENTS}


@func
def __clear(input: list[str], cpu: CPU):
    system('clear')
    return cpu


@func
def __quit(input: list[str], cpu: CPU):
    exit()


func_alias("q", __quit)


completer = NestedCompleter.from_nested_dict(completions)


def handle_console(cpu: CPU, flush_output: bool = False):
    con = cpu._console

    output = con.extract_output(flush=(flush_output or con.need_input))
    while output:
        line, lf, output = output.partition(b'\n')
        line_text = line.decode('utf-8', errors='replace')
        print(f'{ui.BOLD + ui.MAGENTA}Console:{ui.ENDC}{line_text}')

    if con.need_input:
        input_line = input(f'{ui.BOLD + ui.MAGENTA}Console>{ui.ENDC}')
        con.add_input(input_line.encode('utf-8') + b'\n')
        con.need_input = False


def main():
    # grab arguments
    args = sys.argv[1:]

    # grab config file
    path = 'config.yml'
    config = benedict.from_yaml(path)

    # Create CPU
    cpu = CPU(config)

    # Load program
    try:
        cpu.load_program_from_file(args[0])
    except IndexError:
        print_version()
        ui.get_terminal_size()
        ui.print_div()
        print(f"{ui.RED + ui.BOLD}Usage: python main.py <program> [<command> ...]{ui.ENDC}\n")
        exit(1)

    ui.get_terminal_size()
    ui.all_headers(cpu, breakpoints)

    command_queue = deque(args[1:])
    first_prompt = True

    # enter main loop for shell
    previous_command = None
    while True:
        handle_console(cpu)
        if command_queue:
            text = command_queue.popleft()
        else:
            if first_prompt:
                print(f"{ui.BLUE + ui.BOLD}  Press tab for a list of available commands.{ui.ENDC}")
                first_prompt = False
            try:
                text = session.prompt(PROMPT, auto_suggest=AutoSuggestFromHistory(),
                                      completer=completer, complete_while_typing=True)
            except (KeyboardInterrupt, EOFError):
                break
        if text:
            text = '__' + text
        elif previous_command is None:
            continue
        else:
            text = previous_command
        cmd = text.split()[0]
        params = text.split()[1:]
        ui.get_terminal_size()
        fn = funcs.get(cmd, __not_found)
        n_cpu = fn(params, cpu)
        if n_cpu is not None:
            cpu = n_cpu
        previous_command = text


if __name__ == "__main__":
    main()
