import ast
import enum


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
        TWORD = 80
        OWORD = 128
        YWORD = 256
        ZWORD = 512

    def __init__(
        self, radix: NotationRadix = NotationRadix.Hexadecimal, unit=NotationUnit.DWORD
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
            unit = NotationInfo.NotationUnit.DWORD

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
            raise TypeError

    def visit_Expr(self, node: ast.Expr) -> PropertyInfo:
        if isinstance(node.value, ast.Name):
            reg_name = self.visit_Name(node.value)
            return PropertyInfo(reg_name, SliceInfo())
        elif isinstance(node.value, ast.Subscript):
            reg_name, reg_slice = self.visit_Subscript(node.value)
            return PropertyInfo(reg_name, reg_slice)
        else:
            raise TypeError

    def visit_AnnAssign(self, node: ast.AnnAssign) -> tuple[PropertyInfo, NotationInfo]:
        if isinstance(node.target, ast.Name):
            reg_name = self.visit_Name(node.target)
            radix, unit = NotationInfo.decode(self.visit_Name(node.annotation))
            return PropertyInfo(reg_name, SliceInfo()), NotationInfo(radix, unit)
        elif isinstance(node.target, ast.Subscript):
            reg_name, reg_slice = self.visit_Subscript(node.target)
            radix, unit = NotationInfo.decode(self.visit_Name(node.annotation))
            return PropertyInfo(reg_name, reg_slice), NotationInfo(radix, unit)
        else:
            raise TypeError

    def visit_Subscript(self, node: ast.Subscript) -> tuple[str, SliceInfo]:
        reg_name = self.visit_Name(node.value)
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


if __name__ == "__main__":
    RegNotASTVst = RegisterNotationASTVisitor()
    test = RegNotASTVst.parse_register("$rdx[24:]:x64")
    RegNotASTVst.debug_print(test)
