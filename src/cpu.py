from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Callable, Optional

from .bpu import AbstractBPU, AbstractBTB, AbstractRSB, BPU, SimpleBPU, BTB, RSB
from .environ import ConsoleBuffer
from .execution import ExecutionEngine, FaultInfo
from .frontend import Frontend, InstrFrontendInfo
from .instructions import (Instruction, InstructionKind, InstrBranch, InstrJumpRegister,
                           InstrLoad, InstrStore, InstrFlush, InstrSerializing)
from .memory import MemorySubsystem
from .parser import Parser
from .syscalls import dispatch_syscall


SyscallDispatcher = Callable[["CPU", FaultInfo], None]


@dataclass
class CPUStatus:
    """Current status of the CPU."""

    # Whether the CPU is currently still executing a program.
    executing_program: bool

    # FaultInfo as provided by the execution engine if the
    # last tick caused an exception.
    fault_info: Optional[FaultInfo]
    # If a fault has occurred , this variable contains the
    # corresponding microprogram that will be run.
    fault_microprog: Optional[str]

    # List of program counters of instructions that have
    # been issued this tick.
    issued_instructions: list[int]


_snapshots: list[CPU] = []


class CPU:

    _parser: Parser
    _frontend: Optional[Frontend]
    _bpu: AbstractBPU
    _btb: AbstractBTB
    _rsb: AbstractRSB
    _mem: MemorySubsystem
    _exec_engine: ExecutionEngine

    # Index for snapshot list.
    _snapshot_index: int

    _config: dict
    _microprograms: dict[str, tuple[str, list[Instruction]]]

    _symbols: dict[str, int]
    _symbol_index: dict[int, list[str]]

    _exit_status: Optional[int]
    _console: ConsoleBuffer
    _syscalls: Optional[SyscallDispatcher]

    def __init__(self, config: dict):

        self._config = config
        self._parser = Parser.from_default()
        self._mem = MemorySubsystem(config)

        if config["BPU"]["advanced"]:
            self._bpu = BPU(config)
        else:
            self._bpu = SimpleBPU(config)

        self._btb = BTB(config)
        self._rsb = RSB(config)

        # cannot initialize frontend without list of instructions
        # to execute
        self._frontend = None

        # Reservation stations
        self._exec_engine = ExecutionEngine(None, self._mem, self._bpu, self._btb, config)

        # Microprograms
        self._microprograms = {}
        for instr_type, filename in config["Microprograms"].items():
            if filename.lower() == "none":
                continue

            with open(filename, "r") as f:
                source = f.read()

            program = self._parser.parse(source)
            if program.data_segment.data:
                raise RuntimeError(f'Microcode program {instr_type}: '
                                   f'Data in microcode are not supported')
            if program.entry_point != program.text_segment.address:
                raise RuntimeError(f'Microcode program {instr_type}: '
                                   f'Invalid entry point')
            assert program.text_segment.code is not None

            self._microprograms[instr_type.lower()] = (filename, program.text_segment.code)

        self._symbols = {}
        self._symbol_index = {}

        self._exit_status = None
        self._console = ConsoleBuffer()
        self._syscalls = dispatch_syscall

        # Snapshots
        global _snapshots
        self._snapshot_index = 0
        _snapshots = []
        _snapshots.append(copy.deepcopy(self))

    def load_program_from_file(self, path: str):
        """Loads a program given a file path."""
        with open(path, "r") as f:
            source = f.read()
        self.load_program(source)

    def load_program(self, source: str):
        """
        Loads a program given the source code.
        Initializes the frontend and execution engine.
        """
        program = self._parser.parse(source)
        assert program.text_segment.code is not None

        # Initialize frontend
        self._frontend = Frontend(self._bpu, self._btb, self._rsb,
                                  program.text_segment.code, program.entry_point, self._config)
        # Reset reservation stations?
        self._exec_engine = ExecutionEngine(self._frontend, self._mem, self._bpu, self._btb, self._config)
        # Initialize memory
        self._mem.write_blob(program.text_segment.address, program.text_segment.data)
        self._mem.write_blob(program.data_segment.address, program.data_segment.data)

        self._symbols = program.symbols
        self._symbol_index.clear()
        for name, addr in self._symbols.items():
            self._symbol_index.setdefault(addr, []).append(name)

        # take snapshot
        self._take_snapshot()

    def tick(self) -> CPUStatus:
        """
        The tick function that executes one cycles each time it is called.

        Returns:
            status (CPUStatus): An instance of the CPUStatus class containing
                information about the executed cycle. See the top of this file for
                details on this class.
        """

        # check if any program is being executed
        if self._frontend is None:
            return CPUStatus(False, None, None, [])

        cpu_status: CPUStatus = CPUStatus(True, None, None, [])

        # fill execution units
        while self._frontend.get_instr_queue_size() > 0:
            instr_info: InstrFrontendInfo = self._frontend.fetch_instruction_from_queue()
            if self._exec_engine.try_issue(instr_info.instr, instr_info.prediction,
                                           instr_info.addr_prediction):
                self._frontend.pop_instruction_from_queue()
                cpu_status.issued_instructions.append(instr_info.instr.addr)
            else:
                break

        # tick execution engine
        if (fault_info := self._exec_engine.tick()) is not None:
            cpu_status.fault_info = fault_info

            resume_normally: bool = True
            resume_at_pc: int = fault_info.instr.addr

            if fault_info.effect == 'ecall' and self._syscalls:
                # Increment the PC now to allow the system call to re-point it.
                self._frontend.pc = fault_info.instr.addr + 4
                # If the frontend did its work, flushing the queue should not be needed.
                assert self._frontend.get_instr_queue_size() == 0

                self._syscalls(self, fault_info)

                self._frontend.unstall()
                resume_normally = False

            # For faulting memory instructions, we simply skip the instruction.
            # Normally, one would have to register an exception handler. We skip this
            # step for the sake of simplicity.
            elif isinstance(fault_info.instr.ty, (InstrLoad, InstrStore, InstrFlush)):
                resume_at_pc += 4

            # EBREAK requires no special handling. FENCE.I never faults.
            elif isinstance(fault_info.instr.ty, InstrSerializing):
                self._frontend.unstall()
                resume_normally = False

            # Register jumps cause faults when they are mispredicted, and when they go
            # to illegal addresses.
            # Whether the address is illegal cannot be determined within the execution unit
            # because it does not know the length of the instruction list.
            # In the case of an illegal address, we adopt the behavior of a faulting memory
            # access and skip the jump instruction (TODO: add support for actual CPU
            # exceptions).
            elif isinstance(fault_info.instr.ty, InstrJumpRegister):
                next_instr = fault_info.next_instr_addr
                assert next_instr is not None
                if (self._frontend.pc_bounds[0] <= next_instr < self._frontend.pc_bounds[1]
                        and next_instr % 4 == 0):
                    resume_at_pc = next_instr
                else:
                    resume_at_pc += 4

            if resume_normally:
                # We set the pc to the next instruction.
                # It may happen that the last instruction of a program faults, in which case
                # this index will be out of bounds. That's fine though, because the frontend's
                # is_done method checks for this and we will not actually use this
                # out of bounds index.
                self._frontend.pc = resume_at_pc

                self._frontend.flush_instruction_queue()

                # If configured, pick the instruction type's corresponding microprogram
                # and run it.
                filename, microprogram = self._pick_microprogram(fault_info.instr.ty)
                if microprogram is not None:
                    self._frontend.add_micro_program(microprogram)
                    cpu_status.fault_microprog = filename

                # If the instruction that caused the rollback is a branch
                # instruction, we notify the front end which makes sure
                # the correct path is taken next time.
                if isinstance(fault_info.instr.ty, InstrBranch):
                    self._frontend.add_instructions_after_branch(
                        not fault_info.prediction, fault_info.instr.addr
                    )

        # fill up instruction queue
        self._frontend.add_instructions_to_queue()

        # create snapshot
        self._take_snapshot()

        if self._frontend.is_done() and self._exec_engine.is_done():
            return CPUStatus(False, None, None, [])

        return cpu_status

    def get_memory_subsystem(self) -> MemorySubsystem:
        """Returns an instance of the MS class."""
        return self._mem

    def get_frontend(self) -> Optional[Frontend]:
        """
        Returns an instance of the Frontend class if a program is currently
        being executed.

        Otherwise, 'None' is returned.
        """
        return self._frontend

    def get_frontend_or_fail(self) -> Frontend:
        """
        Returns this CPU's Frontend or raises an exception.
        """
        assert self._frontend is not None
        return self._frontend

    def get_bpu(self) -> AbstractBPU:
        """Returns this CPU's BPU."""
        return self._bpu

    def get_btb(self) -> AbstractBTB:
        """Returns this CPU's BTB."""
        return self._btb

    def get_rsb(self) -> AbstractRSB:
        """Returns this CPU's RSB."""
        return self._rsb

    def get_exec_engine(self) -> ExecutionEngine:
        '''Returns an instance of the ExecutionEngine class.'''
        return self._exec_engine

    def _take_snapshot(self) -> None:
        """
        This function creates a snapshot of the current CPU instance by deepcopying
        it and adding an entry to the global snapshot list. Note that the snapshot
        list is not part of the CPU class.
        """
        global _snapshots

        if self._snapshot_index < len(_snapshots) - 1:
            # The snapshot index is not pointing to the last snapshot in the list.
            # This means a snapshot was restored recently. After doing so, it would
            # still have been possible to go forward to newer snapshots again.
            # But, now we create a new snapshot. Rather than keeping multiple lists
            # of snapshots that allow users to switch between different execution
            # paths, we forget about the snapshots that were taken after the point
            # to which we restored.
            # It is important that we copy the cpu instance stored in the snapshot
            # list, rather than using "self.deepcopy()" here. In case this class
            # instance (self) was changed before taking this snapshot, we would
            # be altering the snapshot list at the index pointed to by snapshot_index.
            current_cpu = copy.deepcopy(_snapshots[self._snapshot_index])

            # Now we strip the snapshot list of all more recent invalid snapshots.
            _snapshots = _snapshots[: self._snapshot_index]
            _snapshots.append(current_cpu)

            # Finally, we can add the potentially modified version of this instance
            # to the snapshot list (as the most recent snapshot).

        self._snapshot_index += 1
        cpu_copy = copy.deepcopy(self)

        _snapshots.append(cpu_copy)

    def get_snapshots(self) -> list[CPU]:
        """ Returns the current snapshots. """
        global _snapshots
        return _snapshots

    @staticmethod
    def restore_snapshot(cpu: CPU, steps: int) -> CPU:
        """
        Given a CPU instance, this function returns a snapshot from 'steps' cycles
        in the future or past.

        Paremters:
            cpu (CPU) -- The CPU instance relative to which the snapshot should be chosen.
            steps (int) -- How many time steps away the desired snapshot is.

        Returns:
            CPU: A deepcopy of the corresponding CPU instance from the snapshot list.
        """
        global _snapshots
        if cpu._snapshot_index + steps < 1 or cpu._snapshot_index + steps >= len(_snapshots):
            raise ValueError('Invalid snapshot restoration shift')

        # Returning copies is important, as otherwise a manipulation
        # of the returned cpu instance (for example, calling tick),
        # changes the class that is stored in the snapshot list.
        return copy.deepcopy(_snapshots[cpu._snapshot_index + steps])

    def _pick_microprogram(self, instr_type: InstructionKind) -> tuple[str, list] | tuple[None, None]:
        """
        Returns the filename and set of instructions of a microprogram given
        an instruction type.

        Parameters:
            instr_type (InstructionKind) -- The instruction for which to pick
                the corresponding microprogram.

        Returns:
            tuple[str, list]: A filename of the microprogram and its instructions.
                None if no microprogram could be found.
        """
        key = instr_type.__class__.__name__.lower()
        if key in self._microprograms:
            return self._microprograms[key]
        return None, None
