"""BCM2837 GPIO register access through QEMU QTest."""

from __future__ import annotations

from dataclasses import dataclass

from .qtest import QTestClient

GPIO_BASE = 0x3F200000
GPFSEL_BASE = 0x00
GPSET_BASE = 0x1C
GPCLR_BASE = 0x28
GPLEV_BASE = 0x34
GPIO_COUNT = 54


@dataclass(frozen=True)
class PinState:
    pin: int
    mode: str
    level: int
    function: int


class BCM2837GPIO:
    """Access the BCM2837 GPIO controller in a QEMU raspi3b machine."""

    def __init__(self, qtest: QTestClient):
        self.qtest = qtest

    @staticmethod
    def _validate_pin(pin: int) -> None:
        if (
            isinstance(pin, bool)
            or not isinstance(pin, int)
            or not 0 <= pin < GPIO_COUNT
        ):
            raise ValueError(
                f"GPIO pin must be an integer in range 0..{GPIO_COUNT - 1}"
            )

    @staticmethod
    def _validate_level(level: int) -> None:
        if isinstance(level, bool) or level not in (0, 1):
            raise ValueError("GPIO level must be 0 or 1")

    def _read_reg(self, offset: int) -> int:
        return self.qtest.readl(GPIO_BASE + offset)

    def _write_reg(self, offset: int, value: int) -> None:
        self.qtest.writel(GPIO_BASE + offset, value)

    def function(self, pin: int) -> int:
        self._validate_pin(pin)
        register = GPFSEL_BASE + (pin // 10) * 4
        shift = (pin % 10) * 3
        return (self._read_reg(register) >> shift) & 0b111

    def mode(self, pin: int) -> str:
        fn = self.function(pin)
        if fn == 0:
            return "input"
        if fn == 1:
            return "output"
        return f"alt{fn}"

    def set_mode(self, pin: int, mode: str) -> None:
        self._validate_pin(pin)
        normalized = mode.strip().lower()
        if normalized not in ("input", "in", "output", "out"):
            raise ValueError("Mode must be input/in or output/out")
        fn = 0 if normalized in ("input", "in") else 1
        register = GPFSEL_BASE + (pin // 10) * 4
        shift = (pin % 10) * 3
        mask = 0b111 << shift
        current = self._read_reg(register)
        updated = (current & ~mask) | (fn << shift)
        self._write_reg(register, updated)

    def read(self, pin: int) -> int:
        self._validate_pin(pin)
        bank = pin // 32
        bit = pin % 32
        levels = self._read_reg(GPLEV_BASE + bank * 4)
        return (levels >> bit) & 1

    def write(self, pin: int, level: int) -> None:
        self._validate_pin(pin)
        self._validate_level(level)
        # if self.function(pin) != 1:
        #     raise RuntimeError(f"GPIO {pin} is not configured as an output")
        bank = pin // 32
        bit = pin % 32
        offset = (GPSET_BASE if level else GPCLR_BASE) + bank * 4
        self._write_reg(offset, 1 << bit)

    def state(self, pin: int) -> PinState:
        fn = self.function(pin)
        mode = "input" if fn == 0 else "output" if fn == 1 else f"alt{fn}"
        return PinState(pin=pin, mode=mode, level=self.read(pin), function=fn)
