"""
Shared helpers for safely interpolating configuration values into shell
commands.

Both executors run commands through a shell (LocalExecutor uses
subprocess(shell=True); SSHExecutor uses exec_command, which runs the string
through the remote login shell), so every value that reaches a command string
has to be quoted for the shell that will parse it.

POSIX shells are handled with shlex.quote. cmd.exe has no reliable in-quote
escape for its metacharacters, so values that would require one are rejected
rather than escaped -- see assert_windows_shell_safe.
"""
import os
import shlex

from src.execution.local import LocalExecutor

# cmd.exe has no reliable in-quote escape for these characters (doubling a
# quote does not consistently re-enter quoted state the way CSV/argv rules
# suggest, and `%`/`^`/`&`/`|`/`<`/`>` are all meaningful to cmd.exe's own
# line parser even inside a quoted string in some contexts). Rather than
# attempt string-escaping that cmd.exe won't honor, reject values that would
# require it.
WINDOWS_SHELL_UNSAFE_CHARS = set('"&|^<>%!')

# Control characters get the same treatment, and for a sharper reason: a
# newline inside the command string ends the command at that point. cmd.exe
# does not run what follows -- it discards it -- so a value carrying one
# silently truncates the command instead of failing, which is the worst of the
# three possible outcomes. Verified against cmd.exe rather than assumed.
#
# None of these belongs in a filesystem path or a database credential, so
# rejecting the whole C0 range costs nothing and closes the class rather than
# the one character that prompted it.
WINDOWS_SHELL_UNSAFE_CHARS |= {chr(code) for code in range(0x20)} | {chr(0x7F)}

#: Readable names for the characters that have no printable form, so the error
#: names what is wrong instead of showing an invisible glyph.
_CONTROL_NAMES = {"\n": "newline", "\r": "carriage return", "\t": "tab", "\0": "null"}


def _describe(characters) -> str:
    """Render rejected characters so a person can act on the message."""
    return ", ".join(
        _CONTROL_NAMES.get(char, f"control character {ord(char):#04x}")
        if ord(char) < 0x20 or ord(char) == 0x7F else repr(char)
        for char in sorted(characters)
    )


def assert_windows_shell_safe(value: str, field_name: str, subject: str = "Value") -> None:
    """
    Raise ValueError if `value` contains characters cmd.exe cannot safely quote.

    Args:
        value: the string destined for a cmd.exe command line.
        field_name: human-readable name of the field, used in the message.
        subject: leading noun for the message (e.g. "Database", "Site").
    """
    unsafe = WINDOWS_SHELL_UNSAFE_CHARS.intersection(value or "")
    if unsafe:
        raise ValueError(
            f"{subject} {field_name} contains {_describe(unsafe)}, "
            f"which cannot be safely passed to a Windows shell command. "
            f"Please remove them from the site's {field_name}."
        )


def is_windows_local(executor) -> bool:
    """
    True when `executor` runs commands directly on this Windows host, where
    cmd.exe (not a POSIX shell) parses the command string. Every caller that
    quotes a path/value for shell interpolation needs this to pick the right
    quoting rules -- SSH always talks to a POSIX login shell, so only a local
    Windows executor changes the answer.
    """
    return isinstance(executor, LocalExecutor) and os.name == "nt"


def quote_posix(value: str) -> str:
    """Quote a value for a POSIX shell."""
    return shlex.quote(value or "")


def quote_path(path: str, field_name: str, is_windows: bool, subject: str = "Site") -> str:
    """
    Quote a filesystem path for interpolation into a shell command.

    On POSIX this is shlex.quote. On Windows the value is validated and wrapped
    in double quotes, since cmd.exe cannot escape its own metacharacters.
    """
    if is_windows:
        path = path or ""
        assert_windows_shell_safe(path, field_name, subject)
        # A run of backslashes immediately before the closing quote escapes it,
        # so `C:\sites\mysite\` becomes `"C:\sites\mysite\"` and the argument
        # swallows whatever follows it on the command line -- measured as
        # ['C:\\sites\\mysite" SECOND-ARG'] rather than two arguments.
        #
        # Doubling that run is the documented rule and round-trips exactly,
        # including for a bare drive root where stripping would change `C:\`
        # (the root) into `C:` (the current directory on that drive). Only the
        # trailing run matters: backslashes elsewhere in the value are already
        # literal inside quotes.
        trailing = len(path) - len(path.rstrip("\\"))
        if trailing:
            path = path + "\\" * trailing
        return f'"{path}"'
    return quote_posix(path)
