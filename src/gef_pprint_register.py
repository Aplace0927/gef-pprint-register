from typing import TypedDict
from enum import Enum
from typing import Any
import ast


class Endianess(Enum):
    LITTLE = "LITTLE"
    BIG = "BIG"


class RegisterViewProperties(TypedDict):
    reg_name: str
    reg_bits: int

    view_slice: slice
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


def do_preprocess(argv: list[str]) -> str:
    """
    Split queries by register delimiter.
    """
    return ("".join(argv)).split("$")


class RegisterNotationASTVisitor(ast.NodeVisitor):
    __register_properties: RegisterViewProperties = {
        "reg_name": str,
        "reg_bits": int,
        "view_slice": slice(None, None),
        "view_endianess": Endianess.LITTLE,
        "decodetype_radix": "x",
        "decodetype_unit": 64,
    }

    def view_fetched(self):
        """
        DEBUG PURPOSE.
        """
        print(f"REG_NAME = {self.__register_properties['reg_name']}")
        print(f"REG_BITS = {self.__register_properties['reg_bits']}")
        print(f"VIE_SLIC = {self.__register_properties['view_slice']}")
        print(f"VIE_ENDI = {self.__register_properties['view_endianess']}")
        print(f"DCD_RADX = {self.__register_properties['decodetype_radix']}")
        print(f"DCD_UNIT = {self.__register_properties['decodetype_unit']}")

    def parse_register_notation(self, regs: str) -> ast.Module:
        """
        Parse string into register notation AST.
        """
        return ast.parse(regs)

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
        self.__register_properties["decodetype_unit"] = 64

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
            int(decodetype[1:]) if decodetype[1:] else None
        )
        return self.visit(node.target)

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
    __frame: gdb.Frame = gdb.newest_frame()


class ExtendedRegisterCommand(GenericCommand):
    _cmdline_: str = "rezister"
    _syntax_: str = f"{_cmdline_} {{Register[Beytes]:{{Format}}}} ... {{Register[Bytes]:{{Format}}}}"
    _example_: str = f"\n{_cmdline_} $rax" f"\n{_cmdline_} $rsp[3:]:u32"
    __doc__: str = "Register(including SIMD) formatted pretty-print extension."

    @only_if_gdb_running
    def do_invoke(self, argv):
        if not isinstance(gef.arch, X86_64):
            raise gdb.error("Only available on X86-64 architecture")

        argv = do_preprocess(argv)[1:]

        register_ast_visitor = RegisterNotationASTVisitor()
        register_viewer = RegisterViewer()

        for arg in argv:
            register_ast = register_ast_visitor.parse_register_notation(arg)
            register_parsed = register_ast_visitor.parse_register_ast(register_ast)


register(ExtendedRegisterCommand)
