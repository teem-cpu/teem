"""System call (ECALL) handling."""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Literal, Optional, Union, cast

from .execution import FaultInfo
from .instructions import RegID
from .word import Byte, Word

if TYPE_CHECKING:
    # Avoid circular import.
    from .cpu import CPU


SyscallCallback = Callable[['SystemCall'], None]


MAX_READWRITE = 4096


REGISTERED_SYSCALLS: dict[int, SyscallCallback] = {}


class SystemCall:
    """
    The context of a single system call invocation.
    """

    cpu: CPU
    fault_info: FaultInfo
    callback: Optional[SyscallCallback]

    def __init__(self, cpu: CPU, fault_info: FaultInfo):
        self.cpu = cpu
        self.fault_info = fault_info
        self.callback = None

    def get_register(self, regno: RegID) -> Word:
        "Retrieve the value of the given register."
        result = self.cpu._exec_engine._registers[regno]
        assert isinstance(result, Word)
        return result

    def set_register(self, regno: RegID, value: Word) -> None:
        "Set the indicated register to the given value."
        registers = self.cpu._exec_engine._registers
        assert isinstance(registers[regno], Word)
        registers[regno] = Word.from_int(value)

    def get_number(self) -> Word:
        "Return the number of the current system call."
        # The syscam call number is passed in a7.
        return self.get_register(cast(RegID, 17))

    def get_arg(self, index: Literal[0, 1, 2, 3, 4, 5]) -> Word:
        "Retrieve the given system call argument."
        # a0 through a5 are, conveniently, registers 10 through 15.
        return self.get_register(cast(RegID, 10 + index))

    def set_return(self, value: Word) -> None:
        "Set the system call's return value."
        self.set_register(cast(RegID, 10), value)

    def set_pc(self, addr: int) -> None:
        "Set the address at which execution will resume."
        frontend = self.cpu._frontend
        assert frontend is not None
        assert len(frontend.instr_queue) == 0
        frontend.set_pc(addr)

    def run(self) -> None:
        "Effect the system call's effects on the given CPU instance."
        if self.callback is None:
            self.set_return(Word(-38))  # ENOSYS
        else:
            self.callback(self)


def syscall(number: Union[int, Word]) -> Callable[[SyscallCallback], SyscallCallback]:
    "Decorator for entering a system call into the global registry."
    def register(callback: SyscallCallback) -> SyscallCallback:
        REGISTERED_SYSCALLS[Word.from_int(number).value] = callback
        return callback

    return register


@syscall(-1)
def sys_exit(self: SystemCall):
    "Stop the program's execution."
    self.cpu._exit_status = self.get_arg(0).value
    assert self.cpu._frontend is not None
    self.set_pc(self.cpu._frontend.pc_bounds[1])


@syscall(-2)
def sys_write(self: SystemCall):
    "Print some text to the console."
    bufaddr, bufsize = self.get_arg(0), self.get_arg(1).value

    text_bytes: list[int] = []
    for i in range(min(bufsize, MAX_READWRITE)):
        mem_result = self.cpu._mem.read_byte(bufaddr + Word(i))
        if mem_result.fault:
            self.set_return(Word(-14))  # EFAULT
            return

        text_bytes.append(mem_result.value.value)

    self.cpu._console.add_output(bytes(text_bytes))
    self.set_return(Word(len(text_bytes)))


@syscall(-3)
def sys_read(self: SystemCall):
    bufaddr, bufsize = self.get_arg(0), self.get_arg(1).value

    if not self.cpu._console.has_input:
        # If the input buffer is empty, "block" (by retrying) until it is not.
        self.cpu._console.need_input = True
        self.set_pc(self.fault_info.instr.addr)
        return

    received_bytes = self.cpu._console.read_input(min(bufsize, MAX_READWRITE))
    for i, b in enumerate(received_bytes):
        mem_result = self.cpu._mem.write_byte(bufaddr + Word(i), Byte(b))
        if mem_result.fault:
            # An EFAULT read is not guaranteed not lose data. Too bad.
            self.set_return(Word(-14))  # EFAULT
            return

    self.set_return(Word(len(received_bytes)))


def dispatch_syscall(cpu: CPU, fault_info: FaultInfo) -> None:
    """
    Select which system call is being called and invoke its handler.
    """
    syscall = SystemCall(cpu, fault_info)
    number = syscall.get_number()
    try:
        syscall.callback = REGISTERED_SYSCALLS[number.value]
    except KeyError:
        pass
    syscall.run()
