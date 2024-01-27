from typing import TypedDict
from enum import Enum


class Endianess(Enum):
    LITTLE = "LITTLE"
    BIG = "BIG"


class RegisterViewProperties(TypedDict):
    reg_name: str
    reg_bits: int

    view_slice: tuple[int | None, int | None] | int
    view_endianess: Endianess

    decodetype_radix: str
    decodetype_unit: int | None


def get_register_bits(reg: str) -> int:
    if "xmm" in reg:
        return 128
    if "ymm" in reg:
        return 256
    if "zmm" in reg:
        return 512
    else:
        return 64
