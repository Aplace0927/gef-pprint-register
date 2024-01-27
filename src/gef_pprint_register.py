from gef import *
import gdb

"""
Available formats

rez

"""


class RegisterViewer(GenericCommand):
    _cmdline_: str = "rezister"
    _syntax_: str = (
        f"{_cmdline_} [[[Register][Bytes] [Format]] ... [[Register][Bytes] [Format]]]"
    )
    _example_: str = f"\n{_cmdline_}" f"\n{_cmdline_} "

    @only_if_gdb_running
    def do_invoke(self, argv):
        if not isinstance(gef.arch, X86_64):
            gdb.error("Only available on X86-64 architecture")


class NewCommand(GenericCommand):
    """Dummy new command."""

    _cmdline_ = "newcmd"
    _syntax_ = f"{_cmdline_}"

    @only_if_gdb_running  # not required, ensures that the debug session is started
    def do_invoke(self, argv):
        # let's say we want to print some info about the architecture of the current binary
        print(f"gef.arch={type(gef.arch)}")
        # or showing the current $pc
        print(f"gef.arch.pc={gef.arch.pc:#x}")
        return


register(NewCommand)
