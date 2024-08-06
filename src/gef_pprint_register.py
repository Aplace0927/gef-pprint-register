import ast
import enum
import re
import struct

class NotationInfo:
    class NotationRadix(enum.Enum):
        Hexadecimal = "x"
        Octal = "o"
        SignedDecimal = "d"
        UnsignedDecimal = "u"
        Binary = "b"
        Float = "f"
        Character = "c"

    class NotationUnit(enum.IntEnum):
        BYTE = 8
        WORD = 16
        DWORD = 32
        QWORD = 64
        OWORD = 128
        YWORD = 256
        ZWORD = 512
        DEFAULT = 0

    def __init__(
        self, radix: NotationRadix = NotationRadix.Hexadecimal, unit=NotationUnit.DEFAULT
    ) -> None:
        self.radix = radix
        self.unit = unit

    @staticmethod
    def decode(encoded: str) -> tuple[NotationRadix, NotationUnit]:
        radix_, unit_ = encoded[0], int(encoded[1:])
        try:
            radix = NotationInfo.NotationRadix(radix_)
        except:
            radix = NotationInfo.NotationRadix.Hexadecimal

        try:
            unit = NotationInfo.NotationUnit(unit_)
        except:
            unit = NotationInfo.NotationUnit.DEFAULT

        return radix, unit

class SliceInfo:
    class SliceRange(enum.Enum):
        FROM_MSB = 1023
        TO_LSB = 0

    def __init__(
        self, slice_from: int | SliceRange, slice_to: int | SliceRange
    ) -> None:
        self.slice_from = slice_from
        self.slice_to = slice_to

class PropertyInfo:
    def __init__(self, reg_name: str | None, reg_slice: SliceInfo) -> None:
        self.reg_name = reg_name
        self.reg_slice = reg_slice

class RegisterDump:
    def __init__(self, reg_property: PropertyInfo, reg_notation: NotationInfo) -> None:
        self.reg_property = reg_property
        self.reg_notation = reg_notation


class RegisterNotationASTVisitor(ast.NodeVisitor):
    def parse_register(self, annotation: str) -> RegisterDump:
        reg_ast = ast.parse(annotation.strip("$"))
        return self.visit_Module(reg_ast)

    def debug_print(self, dump: RegisterDump) -> None:
        print(f"name        = {dump.reg_property.reg_name}")
        print(f"slice.from  = {dump.reg_property.reg_slice.slice_from}")
        print(f"slice.to    = {dump.reg_property.reg_slice.slice_to}")
        print(f"type. radix = {dump.reg_notation.radix}")
        print(f"type. unit  = {dump.reg_notation.unit}")

    def visit_Module(self, node: ast.Module) -> RegisterDump:
        if isinstance(node.body[0], ast.Expr):
            reg_property = self.visit_Expr(node.body[0])
            return RegisterDump(reg_property, NotationInfo())
        elif isinstance(node.body[0], ast.AnnAssign):
            reg_property, reg_notation = self.visit_AnnAssign(node.body[0])
            return RegisterDump(reg_property, reg_notation)
        else:
            raise TypeError("Unknown format of register notation")

    def visit_Expr(self, node: ast.Expr) -> PropertyInfo:
        if isinstance(node.value, ast.Name):
            reg_name = self.visit_Name(node.value)
            return PropertyInfo(reg_name, SliceInfo(SliceInfo.SliceRange.FROM_MSB, SliceInfo.SliceRange.TO_LSB))
        elif isinstance(node.value, ast.Subscript):
            reg_name, reg_slice = self.visit_Subscript(node.value)
            return PropertyInfo(reg_name, reg_slice)
        else:
            raise TypeError("Unknown format of register property")

    def visit_AnnAssign(self, node: ast.AnnAssign) -> tuple[PropertyInfo, NotationInfo]:
        if isinstance(node.target, ast.Name):
            reg_name = self.visit_Name(node.target)
            
            if not isinstance(node.annotation, ast.Name):
                raise TypeError("Register annotation must be string constant")

            radix, unit = NotationInfo.decode(self.visit_Name(node.annotation))
            return PropertyInfo(reg_name, SliceInfo(SliceInfo.SliceRange.FROM_MSB, SliceInfo.SliceRange.TO_LSB)), NotationInfo(radix, unit)

        elif isinstance(node.target, ast.Subscript):
            reg_name, reg_slice = self.visit_Subscript(node.target)

            if not isinstance(node.annotation, ast.Name):
                raise TypeError("Register annotation must be string constant")

            radix, unit = NotationInfo.decode(self.visit_Name(node.annotation))
            return PropertyInfo(reg_name, reg_slice), NotationInfo(radix, unit)
        else:
            raise TypeError("Unknown format of register property with notation")

    def visit_Subscript(self, node: ast.Subscript) -> tuple[str, SliceInfo]:
        if not isinstance(node.value, ast.Name):
            raise TypeError("Register name must be string constant")

        reg_name = self.visit_Name(node.value)

        if not isinstance(node.slice, ast.Slice):
            raise TypeError("Register must be sliced")

        slice_from, slice_to = self.visit_Slice(node.slice)
        return reg_name, SliceInfo(slice_from, slice_to)

    def visit_Slice(
        self, node: ast.Slice
    ) -> tuple[int | SliceInfo.SliceRange, int | SliceInfo.SliceRange]:
        if isinstance(node.lower, ast.Constant):
            slice_from = self.visit_Constant(node.lower)
        else:
            slice_from = SliceInfo.SliceRange.FROM_MSB

        if isinstance(node.upper, ast.Constant):
            slice_to = self.visit_Constant(node.upper)
        else:
            slice_to = SliceInfo.SliceRange.TO_LSB

        return slice_from, slice_to

    def visit_Name(self, node: ast.Name) -> str:
        return node.id

    def visit_Constant(self, node: ast.Constant) -> int:
        return node.value

class RegisterRetrieveHook:
    def __init__(self, target_regex: str, hook, length = 1) -> None:
        self.target = target_regex
        self.hook = hook
        self.len = length


class RegisterValueRetriever:
    def __init__(self, hooks: list[RegisterRetrieveHook]) -> None:
        self._hooks = hooks
    
    def apply_slice(self, val: int, slice: SliceInfo):
        if slice.slice_from != SliceInfo.SliceRange.FROM_MSB:
            val &= ((1 << slice.slice_from) - 1)
        if slice.slice_to != SliceInfo.SliceRange.TO_LSB:
            val >>= slice.slice_to
        return val        

    def retrieve_value(self, prop: PropertyInfo) -> None | int:
        for hook in self._hooks:
            if re.findall(hook.target, prop.reg_name) != []:
                reg = gdb.parse_and_eval('$' + hook.hook(prop.reg_name))
                if reg.type.code == gdb.TYPE_CODE_VOID:
                    return None
                else:
                    res = 0
                    for idx in range(hook.len):
                        res |= (int(reg[idx]) << (64 * idx))
                    return self.apply_slice(res, prop.reg_slice)
        reg = gdb.parse_and_eval('$' + prop.reg_name)
        if reg.type.code == gdb.TYPE_CODE_VOID:
            return None
        else:
            return self.apply_slice(int(reg), prop.reg_slice)

    def retrieve_prev_value(self, prop: PropertyInfo) -> None | int:
        ctx_cmd = gef.gdb.commands["context"]
        assert isinstance(ctx_cmd, ContextCommand)
        old_reg = ctx_cmd.old_registers.get('$' + prop.reg_name)
        if old_reg is None:
            return None
        else:
            return self.apply_slice(int(old_reg), prop.reg_slice)

class RegisterSizeIndex:
    def __init__(self, regex: str, size) -> None:
        self.regex = regex
        self.size = size

class RegisterSizeDictionary:
    def __init__(self, indices: list[RegisterSizeIndex]) -> None:
        self.indices = indices

    def __getitem__(self, target: str):
        for ind in self.indices:
            if re.findall(ind.regex, target) != []:
                return ind.size
        
class RegisterPrintHook:
    def __init__(self, target_regex: str) -> None:
        self.target = target_regex
    
    def print_register(reg_value: int):
        pass

class EFLAGSRegisterPrintHook(RegisterPrintHook):
    def __init__(self, target_regex: str) -> None:
        super().__init__(target_regex)

    def print_register(value: int, old_value: int):
        pass


class RegisterPrintFormatter:
    def __init__(self, hooks: list[RegisterPrintHook]) -> None:
        self._hooks = hooks

    def formatted_value(self, radix: NotationInfo.NotationRadix, unit: NotationInfo.NotationUnit, value: int):
        match (radix, unit):
            case (NotationInfo.NotationRadix.Hexadecimal, _):
                return f"{value:#0{(unit // 4) + 2}x}"
            case (NotationInfo.NotationRadix.Octal, _):
                return f"{value:#0{unit // 3 + 2}o}"
            case (NotationInfo.NotationRadix.SignedDecimal, _):
                if value >= (1 << (unit - 1)):
                    return str(-(value ^ ((1 << unit) - 1)))
                else:
                    return str(value)
            case (NotationInfo.NotationRadix.UnsignedDecimal, _):
                return str(value)
            case (NotationInfo.NotationRadix.Binary, _):
                return f"{value:#0{unit + 2}b}"
            case (NotationInfo.NotationRadix.Float, NotationInfo.NotationUnit.WORD):    # bfloat (16bit)
                return struct.unpack("e", int.to_bytes(value, 2, "little"))[0]
            case (NotationInfo.NotationRadix.Float, NotationInfo.NotationUnit.DWORD):   # float (32bit)
                return struct.unpack("f", int.to_bytes(value, 4, "little"))[0]
            case (NotationInfo.NotationRadix.Float, NotationInfo.NotationUnit.QWORD):    # bfloat (64bit)
                return struct.unpack("d", int.to_bytes(value, 8, "little"))[0]
            case (NotationInfo.NotationRadix.Character, NotationInfo.NotationUnit.BYTE): # char
                pass
            case _ : # Unsupported formats.
                return


    def string_by_unit_and_format(self, radix: NotationInfo.NotationRadix, unit: NotationInfo.NotationUnit, field_width: int, value: int):
        if unit != NotationInfo.NotationUnit.DEFAULT:
            res = []
            for _ in range(max(field_width // (unit // 8), 1)):
                res.append(value & ((1 << unit) - 1))
                value >>= unit
            res = [self.formatted_value(radix, unit, v) for v in res]
            if len(res) == 1:
                return res[0]
            else:
                return res
        else:
            return self.formatted_value(radix, field_width * 8, value)

    def string_register(self, reg_notation: NotationInfo, field_width: int, value: None | int) -> None | str:
        if value is None:
            return None
        return self.string_by_unit_and_format(reg_notation.radix, reg_notation.unit, field_width, value)


@register
class ExtendedRegisterCommand(GenericCommand):
    _cmdline_: str = "rezister"
    _syntax_: str = (
        f"{_cmdline_} {{Register[Bytes]:{{Format}}}} ... {{Register[Bytes]:{{Format}}}}"
    )
    _example_: str = f"\n{_cmdline_} $rax" f"\n{_cmdline_} $rsp[3:]:u32"
    __doc__: str = "Register(including SIMD) formatted pretty-print extension."

    if not isinstance(gef.arch, X86_64):
        raise gdb.error("Only available on X86-64 architecture")

    _reg_sizes_ = {}
    _reg_groups_ = []

    _RegisterASTVisitor = RegisterNotationASTVisitor()
    _RegisterValueRetriever = RegisterValueRetriever([
        RegisterRetrieveHook("xmm[0-9]+", lambda xmm: xmm + ".v2_int64", 2),
        RegisterRetrieveHook("ymm[0-9]+", lambda ymm: ymm + ".v4_int64", 4)
    ])

    _RegisterPrintFormatter = RegisterPrintFormatter([
        EFLAGSRegisterPrintHook("eflags")
    ])

    @only_if_gdb_running
    @parse_arguments(
        {"registers": [""]}, {f"--{groupname}": False for groupname in _reg_groups_}
    )
    def do_invoke(self, argv, **kwargs):
        args = kwargs["arguments"]
        if len(self._reg_sizes_) == 0:
            self._reg_sizes_ = {
                reg.split()[0]: int(reg.split()[4])
                for reg in gdb.execute("maint print registers", to_string=True).splitlines()[
                    1:-1
                ] if reg.split()[0] != "''"
            }
        
        if len(self._reg_groups_) == 0:
            self._reg_groups_ = [
                group.split()[0]
                for group in gdb.execute("maint print reggroups", to_string=True).splitlines()[
                    1:
                ]
            ]

        if args.registers != ['']:
            for reg in args.registers:
                parsed = self._RegisterASTVisitor.parse_register(reg)
                curr_value = self._RegisterValueRetriever.retrieve_value(parsed.reg_property)
                prev_value = self._RegisterValueRetriever.retrieve_prev_value(parsed.reg_property)
                field_width = self._reg_sizes_.get(parsed.reg_property.reg_name)
                curr_string = self._RegisterPrintFormatter.string_register(parsed.reg_notation, field_width, curr_value)
                prev_string = self._RegisterPrintFormatter.string_register(parsed.reg_notation, field_width, prev_value)

                if prev_string is None:
                    if isinstance(curr_string, list):
                        out = "["
                        out += ", ".join([f"{Color.colorify(sub, 'yellow')}" for sub in curr_string])
                        out += "]"
                    else:
                        out = f"{Color.colorify(curr_string, 'yellow')}"

                else:
                    last_same = lambda p, q: len(p) if len(diff := [idx for idx, (cur, prev) in enumerate(zip(p, q)) if cur != prev]) == 0 else min(diff)
                    if isinstance(curr_string, list):
                        out = "["
                        out += ", ".join([Color.colorify(cur[:last_same(cur, prv)], 'yellow')+Color.colorify(cur[last_same(cur, prv):], 'yellow bold') for cur, prv in zip(curr_string, prev_string)])
                        out += "]"
                    else:
                        out = f"{Color.colorify(curr_string[:last_same(curr_string, prev_string)], 'yellow')}{Color.colorify(curr_string[last_same(curr_string, prev_string):], 'yellow bold')}"

                print(out)
        #for group in self._reg_groups_:
        #    if args.__getattribute__(group):
        #        for reg in _reg_group_dict_[group]:
        #            parsed = self._RegisterASTVisitor.parse_register(reg)
        #            parsed = modify_notation_for_group(parsed, group)
        #            print_register_with_format(parsed)


register_external_command(ExtendedRegisterCommand())
