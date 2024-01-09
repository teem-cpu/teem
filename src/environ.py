"""Interaction with the world beyond the emulator."""

from __future__ import annotations


class ConsoleBuffer:
    """
    Input/output buffers for a text console.
    """

    in_queue: bytes
    out_queue: bytes
    need_input: bool

    def __init__(self) -> None:
        self.in_queue = b''
        self.out_queue = b''
        self.need_input = False

    @property
    def has_input(self) -> bool:
        "Check whether there is any queued input."
        return bool(self.in_queue)

    @property
    def has_output(self) -> bool:
        "Check whether there is any queued output."
        return bool(self.out_queue)

    def add_input(self, data: bytes) -> None:
        "Add the given bytes to the input queue."
        self.in_queue += data

    def add_output(self, data: bytes) -> None:
        "Add the given bytes to the output queue."
        self.out_queue += data

    def read_input(self, max_amount: int) -> bytes:
        "Extract up to the given amount of bytes from the input queue."
        result = self.in_queue[:max_amount]
        self.in_queue = self.in_queue[max_amount:]
        return result

    def extract_output(self, flush=False) -> bytes:
        "Extract output queue contents, disregarding line boundaries if flush is true."
        if flush:
            result = self.out_queue
            self.out_queue = b''
            return result
        else:
            result, lf, self.out_queue = self.out_queue.rpartition(b'\n')
            return result + lf
