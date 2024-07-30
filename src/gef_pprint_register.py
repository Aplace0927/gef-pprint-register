from ast_formatter import RegisterNotationASTVisitor, RegisterDump


def print_register_with_format(dmp: RegisterDump) -> None:
    pass


def modify_notation_for_group(dmp: RegisterDump, group: str) -> None:
    pass


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

    _reg_types_ = {
        reg.split()[0]: reg.split()[-2]
        for reg in gdb.execute("maint print registers", to_string=True).splitlines()[
            1:-1
        ]
    }
    _reg_groups_ = [
        group.split()[0]
        for group in gdb.execute("maint print reggroups", to_string=True).splitlines()[
            1:
        ]
    ]
    _reg_group_dict_ = {}

    _RegisterASTVisitor = RegisterNotationASTVisitor()

    @only_if_gdb_running
    @parse_arguments(
        {"registers": [""]}, {f"--{groupname}": False for groupname in _reg_groups_}
    )
    def do_invoke(self, argv, **kwargs):
        args = kwargs["arguments"]
        for reg in self.registers:
            parsed = RegisterNotationASTVisitor.parse_register(reg)
            print_register_with_format(parsed)

        for group in self._reg_groups_:
            if args.__getattribute__(group):
                for reg in _reg_group_dict_[group]:
                    parsed = RegisterNotationASTVisitor.parse_register(reg)
                    parsed = modify_notation_for_group(parsed, group)
                    print_register_with_format(parsed)


register_external_command(ExtendedRegisterCommand())
