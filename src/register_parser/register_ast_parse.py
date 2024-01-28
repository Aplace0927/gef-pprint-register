from register_property import RegisterViewProperties, Endianess, get_register_bits
from typing import Any
import ast


def do_preprocess(argv: list[str]) -> str:
    """
    Split queries by register delimiter.
    """
    return ("".join(argv)).split("$")

class RegisterNotationASTVisitor(ast.NodeVisitor):
    __register_properties: RegisterViewProperties = {
        "view_slice": (None, None),
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

    def do_parse(self, node: ast.Module) -> RegisterViewProperties:
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
        self.__register_properties["view_slice"] = (None, None)
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
        self.__register_properties["reg_bits"] = get_register_bits(
            self.__register_properties["reg_name"]
        )

        if type(self.__register_properties["view_slice"]) == tuple:
            lower = self.__register_properties["view_slice"][0]
            upper = self.__register_properties["view_slice"][1]
            self.__register_properties["view_slice"] = (
                lower if lower else self.__register_properties["reg_bits"] - 1,
                upper if upper else 0,
            )

            lower = self.__register_properties["view_slice"][0]
            upper = self.__register_properties["view_slice"][1]
            if lower < upper:
                self.__register_properties["view_endianess"] = Endianess.BIG

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
        self.visit(node.target)
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
            self.__register_properties["view_slice"] = self.visit_Constant(node.slice)

        self.visit_Name(node.value)
        return

    """
    Following function visits nodes with "primitive" types, and returns its data. 
    """

    def visit_Name(self, node: ast.Name) -> str:
        return node.id

    def visit_Slice(self, node: ast.Slice) -> tuple[int, int]:
        upper = self.visit_Constant(node.upper)
        lower = self.visit_Constant(node.lower)
        return lower, upper

    def visit_Constant(self, node: ast.Constant) -> None | int:
        if not isinstance(node, ast.Constant):
            return None
        return node.value


    @staticmethod
    def parse_register_notation(regs: str) -> ast.Module:
        """
        Parse string into register notation AST.
        """
        return ast.parse(regs)

TEST_STR = """
    $rdi
    $r9[3:]
    $rsi[:4]
    $xmm8
    $r7[:]
    $rbp[1]
    $r12:d16
    $rcx:x32
    $rax[:]:u64
    $rbx[1:3]:o32
    $r8[5:]:x32
    $ymm5[32:16]:c
    $zmm0[0:16]:b16

"""

DEBUG = True

if __name__ == "__main__":
    analysis = do_preprocess(TEST_STR)[1:]

    reg_ast_visitor = RegisterNotationASTVisitor()

    for query in analysis:
        reg_ast = ast.parse(query)  # AST of each query
        reg_ast_visitor.visit(reg_ast)  # Start visiting from root

        if DEBUG:
            print("-" * 30)
            reg_ast_visitor.view_fetched()
