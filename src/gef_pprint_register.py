from typing import TypedDict
from enum import Enum
from typing import Any
from itertools import product
from functools import reduce
from operator import or_
from math import ceil
import ast
import struct


class Endianess(Enum):
    LITTLE = "LITTLE"
    BIG = "BIG"


class RegisterViewProperties(TypedDict):
    reg_name: str
    reg_bits: int

    view_slice: slice
    view_endianess: Endianess

    decodetype_radix: str
    decodetype_unit: int


def get_register_bits(reg: str) -> int:
    if "xmm" in reg:
        return 128
    if "ymm" in reg:
        return 256
    if "zmm" in reg:
        return 512
    else:
        return 64


def do_preprocess(argv: list[str]) -> str:
    """
    Split queries by register delimiter.
    """
    return ("".join(argv)).split("$")


def fold64(expand: list[int], ln: int) -> int:
    expand = [int(expand[idx]) for idx in range(ln)]
    return reduce(or_, [x << (idx * 64) for idx, x in enumerate(expand)])


fmt_u = lambda x, n: str(x)
fmt_d = lambda x, n: str(((x & (~(1 << n))) ^ (1 << (n - 1))) - (1 << (n - 1)))
fmt_b = lambda x, n: f"{x:#0{n+2}b}"
fmt_o = lambda x, n: f"{x:#0{ceil(n // 3)+2}o}"
fmt_x = lambda x, n: f"{x:#0{ceil(n // 4)+2}x}"


def fmt_f(x, n):
    if n == 32:
        return str(struct.unpack(">f", struct.pack(">l", x))[0])
    elif n == 64:
        return str(struct.unpack(">d", struct.pack(">q", x))[0])
    else:
        raise gef.error("Invalid floating point size")


def fmt_c(x, n) -> str:
    string = ""
    for _ in range(n // 8):
        ch = x & 0xFF
        x >>= 8
        if ch == 0xA:
            string += chr(0x21B5)
        elif ch == 0x20:
            string += chr(0x2423)
        elif ch == 0x7F:
            string += chr(0x2421)
        elif ch & 0x7F < 0x20:
            if ch > 0x7F:
                string += "."
            else:
                string += chr(0x2400 + ch)
        else:
            string += chr(ch)

    return string


xmm_register: tuple[str, ...] = tuple(f"$xmm{idx}" for idx in range(32))
ymm_register: tuple[str, ...] = tuple(f"$ymm{idx}" for idx in range(32))
zmm_register: tuple[str, ...] = tuple(f"$zmm{idx}" for idx in range(32))
simd_register: tuple[str, ...] = xmm_register + ymm_register + zmm_register


class RegisterNotationASTVisitor(ast.NodeVisitor):
    __register_properties: RegisterViewProperties = {}

    def parse_register_notation(self, regs: str) -> ast.Module:
        """
        Parse string into register notation AST.
        """
        return ast.parse(regs.strip("$"))

    def parse_register_ast(self, node: ast.Module) -> RegisterViewProperties:
        self.visit_Module(node)
        return self.__register_properties

    def visit_Module(self, node: ast.Module) -> Any:
        """
        Visit main body of expression, with reset/complementing register properties on
        prologue/epilogue of visiting.
        """

        """
        Reset register properties at the prologue of register fetching
        """
        self.__register_properties["view_slice"] = slice(None, None)
        self.__register_properties["view_endianess"] = Endianess.LITTLE
        self.__register_properties["decodetype_radix"] = "x"
        self.__register_properties["decodetype_unit"] = 0

        """
        Do register fetch by visiting AST Nodes.
        """
        if isinstance(node.body[0], ast.Expr):
            self.visit_Expr(node.body[0])
        elif isinstance(node.body[0], ast.AnnAssign):
            self.visit_AnnAssign(node.body[0])

        """
        Set undetermined register properties at the epilogue of register fetching.
        """
        register_bits = get_register_bits(self.__register_properties["reg_name"])
        self.__register_properties["reg_bits"] = register_bits
        self.__register_properties["decodetype_unit"] = (
            self.__register_properties["decodetype_unit"] or register_bits
        )

        lower = (
            self.__register_properties["view_slice"].start
            if self.__register_properties["view_slice"].start is not None
            else register_bits // 8
        )
        upper = (
            self.__register_properties["view_slice"].stop
            if self.__register_properties["view_slice"].stop is not None
            else 0
        )

        if lower < upper:
            self.__register_properties["view_endianess"] = Endianess.BIG

        self.__register_properties["view_slice"] = slice(
            min(lower, upper), max(lower, upper)
        )

        return

    def visit_Expr(self, node: ast.Expr) -> Any:
        """
        Visit `ast.Expr` node.
        Only visit unless there is `ast.AnnAssign` node for explicit typing.
        """

        if isinstance(node.value, ast.Name):
            self.__register_properties["reg_name"] = self.visit_Name(node.value)
        elif isinstance(node.value, ast.Subscript):
            self.visit_Subscript(node.value)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> Any:
        """
        Visit `ast.AnnAssign` node.
        Only visit if there is `ast.AnnAssign` node for explicit typing,
        and keep visiting its child `ast.AnnAssign.target` node to fetch data.
        """

        decodetype = self.visit_Name(node.annotation)
        self.__register_properties["decodetype_radix"] = decodetype[0]
        self.__register_properties["decodetype_unit"] = (
            int(decodetype[1:]) if decodetype[1:] else 0
        )

        if isinstance(node.target, ast.Name):
            self.__register_properties["reg_name"] = self.visit_Name(node.target)
        elif isinstance(node.target, ast.Subscript):
            self.visit_Subscript(node.target)
        return

    def visit_Subscript(self, node: ast.Subscript) -> Any:
        """
        Visit `ast.Subscript` node for subscripting or slicing.
        Child node `ast.Subscript.slice` is either `ast.Slice` (slicing) or `ast.Constant` (subscripting),
        and keep visiting them.
        """

        self.__register_properties["reg_name"] = self.visit_Name(node.value)

        if isinstance(node.slice, ast.Slice):
            self.__register_properties["view_slice"] = self.visit_Slice(node.slice)

        elif isinstance(node.slice, ast.Constant):
            index = self.visit_Constant(node.slice)
            self.__register_properties["view_slice"] = slice(index + 1, index)

        return self.visit_Name(node.value)

    """
    Following function visits nodes with "primitive" types, and returns its data. 
    """

    def visit_Name(self, node: ast.Name) -> str:
        return node.id

    def visit_Slice(self, node: ast.Slice) -> slice:
        upper = self.visit_Constant(node.upper)
        lower = self.visit_Constant(node.lower)
        return slice(lower, upper)

    def visit_Constant(self, node: ast.Constant) -> None | int:
        if not isinstance(node, ast.Constant):
            return None
        return node.value


class RegisterViewer:
    __register_properties: RegisterViewProperties
    __frame: gdb.Frame

    def __fetch_bytes(self, register_prop: RegisterViewProperties):
        reg_name = register_prop["reg_name"]
        reg_bits = register_prop["reg_bits"]
        reg_raw = self.__frame.read_register(reg_name)
        reg_val: int
        match reg_bits:
            case 512:
                reg_val = fold64(reg_raw["v8_int64"], 512 // 64)
            case 256:
                reg_val = fold64(reg_raw["v4_int64"], 256 // 64)
            case 128:
                reg_val = fold64(reg_raw["v2_int64"], 128 // 64)
            case 64:
                reg_val = int(reg_raw)

            case _:
                raise gdb.error("Invalid register size")
        return reg_val

    def __extract_bytes(
        self, register_prop: RegisterViewProperties, fetched: int
    ) -> int:
        lower = round(register_prop["view_slice"].start * 8)
        upper = round(register_prop["view_slice"].stop * 8)
        bitmask = ((1 << int(upper)) - 1) ^ ((1 << int(lower)) - 1)

        return (bitmask & fetched) >> lower

    def __chop_bytes(
        self, register_prop: RegisterViewProperties, extracted: int
    ) -> list[int]:
        lower = round(register_prop["view_slice"].start * 8)
        upper = round(register_prop["view_slice"].stop * 8)

        fmt_unit = register_prop["decodetype_unit"]

        chopped = []
        for _ in range(ceil((upper - lower) / fmt_unit)):
            chopped.append(extracted & ((1 << fmt_unit) - 1))
            extracted >>= fmt_unit

        return chopped

    def __apply_format(
        self, register_prop: RegisterViewProperties, chopped: list[int]
    ) -> str:
        fmt_radix = register_prop["decodetype_radix"]
        fmt_unit = register_prop["decodetype_unit"]
        if fmt_radix == "c":
            fmt_unit = int(
                (register_prop["view_slice"].stop - register_prop["view_slice"].start)
                * 8
            )

        fmt_func = {
            "u": fmt_u,
            "d": fmt_d,
            "b": fmt_b,
            "o": fmt_o,
            "x": fmt_x,
            "f": fmt_f,
            "c": fmt_c,
        }

        chopped_value = [fmt_func[fmt_radix](item, fmt_unit) for item in chopped]

        if len(chopped_value) == 1:
            return chopped_value[0]
        else:
            return "[" + ", ".join(chopped_value) + "]"

    def show_gp_registers(self, register_prop: RegisterViewProperties, **kwargs) -> str:
        self.__frame = gdb.newest_frame()

        code_color = gef.config["theme.address_code"]
        stack_color = gef.config["theme.address_stack"]
        heap_color = gef.config["theme.address_heap"]

        unchanged_color = gef.config["theme.registers_register_name"]
        changed_color = gef.config["theme.registers_value_changed"]

        string_color = gef.config["theme.dereference_string"]

        max_width: int = max(map(len, gef.arch.all_registers)) + 1

        register_name: str = register_prop["reg_name"]

        register_raw: int = self.__fetch_bytes(register_prop)
        register_extracted: int = self.__extract_bytes(register_prop, register_raw)
        register_chopped: list[int] = self.__chop_bytes(
            register_prop, register_extracted
        )
        register_value: str = self.__apply_format(register_prop, register_chopped)

        if register_raw == ContextCommand.old_registers.get("$" + register_name, 0):
            color = unchanged_color
        else:
            color = changed_color

        line = f"{Color.colorify(('$' + register_name).ljust(max_width, ' '), color)}: "

        addr = lookup_address(align_address(register_extracted))
        if addr.valid:
            if addr.is_in_text_segment():
                line += Color.colorify(register_value, code_color)
            elif addr.is_in_heap_segment():
                line += Color.colorify(register_value, heap_color)
            elif addr.is_in_stack_segment():
                line += Color.colorify(register_value, stack_color)
            else:
                line += register_value
        else:
            line += register_value

        addrs = dereference_from(register_raw)

        if len(addrs) > 1:
            sep = f" {RIGHT_ARROW} "
            line += sep
            line += sep.join(addrs[1:])

        return line

    def show_special_registers(
        self, register_prop: RegisterViewProperties, **kwargs
    ) -> str:
        self.__frame = gdb.newest_frame()

        unchanged_color = gef.config["theme.registers_register_name"]
        changed_color = gef.config["theme.registers_value_changed"]

        register_name: str = register_prop["reg_name"]

        register_raw: int = self.__fetch_bytes(register_prop)
        register_extracted: int = self.__extract_bytes(register_prop, register_raw)
        register_chopped: list[int] = self.__chop_bytes(
            register_prop, register_extracted
        )
        register_value: str = self.__apply_format(register_prop, register_chopped)

        if register_raw == ContextCommand.old_registers.get("$" + register_name, 0):
            color = unchanged_color
        else:
            color = changed_color

        return f"{Color.colorify('$' + register_name, color)}: {gef.arch.register('$' + register_name):#04x} "

    def show_flag_registers(
        self, register_prop: RegisterViewProperties, **kwargs
    ) -> str:
        self.__frame = gdb.newest_frame()
        return gef.arch.flag_register_to_human()

    def show_simd_registers(
        self, register_prop: RegisterViewProperties, **kwargs
    ) -> str:
        self.__frame = gdb.newest_frame()

        unchanged_color = gef.config["theme.registers_register_name"]
        changed_color = gef.config["theme.registers_value_changed"]

        string_color = gef.config["theme.dereference_string"]

        max_width: int = max(map(len, gef.arch.all_registers + simd_register)) + 1

        register_name: str = register_prop["reg_name"]

        register_raw: int = self.__fetch_bytes(register_prop)
        register_extracted: int = self.__extract_bytes(register_prop, register_raw)
        register_chopped: list[int] = self.__chop_bytes(
            register_prop, register_extracted
        )
        register_value: str = self.__apply_format(register_prop, register_chopped)

        if register_raw == ContextCommand.old_registers.get("$" + register_name, 0):
            color = unchanged_color
        else:
            color = changed_color

        line = f"{Color.colorify(('$' + register_name).ljust(max_width, ' '), color)}: "
        line += Color.colorify(register_value, string_color)
        return line


class ExtendedRegisterCommand(GenericCommand):
    _cmdline_: str = "rezister"
    _syntax_: str = (
        f"{_cmdline_} {{Register[Beytes]:{{Format}}}} ... {{Register[Bytes]:{{Format}}}}"
    )
    _example_: str = f"\n{_cmdline_} $rax" f"\n{_cmdline_} $rsp[3:]:u32"
    __doc__: str = "Register(including SIMD) formatted pretty-print extension."

    @only_if_gdb_running
    @parse_arguments({"registers": [""]}, {})
    def do_invoke(self, argv, **kwargs):
        if not isinstance(gef.arch, X86_64):
            raise gdb.error("Only available on X86-64 architecture")

        args = kwargs["arguments"]
        register_ast_visitor = RegisterNotationASTVisitor()
        register_viewer = RegisterViewer()

        if args.registers[0] == "":
            args.registers = gef.arch.all_registers + zmm_register

        gpr_line: str = ""
        special_line: str = ""
        flag_line: str = ""
        simd_line: str = ""

        for reg in args.registers:
            register_ast = register_ast_visitor.parse_register_notation(reg)
            register_parsed = register_ast_visitor.parse_register_ast(register_ast)

            if "$" + register_parsed["reg_name"] in gef.arch.gpr_registers:
                gpr_line += register_viewer.show_gp_registers(register_parsed) + "\n"
            elif "$" + register_parsed["reg_name"] in gef.arch.special_registers:
                special_line += (
                    register_viewer.show_special_registers(register_parsed) + " "
                )
            elif "$" + register_parsed["reg_name"] == gef.arch.flag_register:
                flag_line += register_viewer.show_flag_registers(register_parsed) + " "
            elif "$" + register_parsed["reg_name"] in simd_register:
                simd_line += register_viewer.show_simd_registers(register_parsed) + "\n"

        if gpr_line:
            gef_print(gpr_line, end="")
        if special_line:
            gef_print(special_line)
        if flag_line:
            gef_print(flag_line)
        if simd_line:
            gef_print(simd_line)


register_external_command(ExtendedRegisterCommand())
