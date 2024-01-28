import os
import sys
import importlib.util


"""
TODO:
Check the path to the extension from environment variable or ~/.gdbinit file.
Try dynamic module loading from deducted path. If unknown, raise error.
"""
if os.environ.get("GEF_EXT_PPRINT_REG"):
    spec = importlib.util.spec_from_file_location("register_ast_parse", os.environ["GEF_EXT_PPRINT_REG"] + "/src/register_parser/__init__.py")
    register_parser = importlib.util.module_from_spec(spec)
    sys.modules["register_ast_parse"] = register_parser
    spec.loader.exec_module(register_parser)
else:
    # TODO: Parse from ~/.gdbinit to fetch the extension source directory
    raise EnvironmentError("Unknown path!")



class ExtendedRegisterCommand(GenericCommand):
    _cmdline_: str = "rezister"
    _syntax_: str = (
        f"{_cmdline_} {{Register[Beytes]:{{Format}}}} ... {{Register[Bytes]:{{Format}}}}"
    )
    _example_: str = f"\n{_cmdline_}" f"\n{_cmdline_} "

    @only_if_gdb_running
    def do_invoke(self, argv):
        if not isinstance(gef.arch, X86_64):
            gdb.error("Only available on X86-64 architecture")

        argv = do_preprocess(argv)
        register_ast_visitor = RegisterNotationASTVisitor()

        for arg in argv:
            register_ast = RegisterNotationASTVisitor.parse_register_notation(arg)
            ast_result = register_ast_visitor.parse_register_notation(register_ast)
            print(ast_result)

register_external_command(ExtendedRegisterCommand())
