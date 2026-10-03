"""The twilite telnet protocol as pure functions: line splitting, parsing, commands.

Everything here matches what a *Coincident Counter - Telnet Server V3.00* sent and
accepted on 2026-10-03 (see ``doc/protocol.md``). The device sends no telnet option
negotiation and does not echo, so plain lines over TCP are all there is.
"""

from __future__ import annotations

import re

from twilite.sample import Sample

###############################################################################
# Device facts                                                                #
###############################################################################

#: Meaning of the numbers after ``[n]`` on a ``showc`` line, and of ``Counter 1..3``
#: in the ``ccnt`` reply, in order. Values beyond these (the two ``0.0`` analog fields)
#: go to ``Sample.raw_extra``. Checked with a source at one detector. PSAMPLE numbers
#: its channels the other way round (channel 1 = coincidences).
FIELD_ORDER: tuple[str, ...] = ("singles1", "singles2", "coincidences")

#: Every line in both directions ends in ``\r\n``.
EOL = b"\r\n"

#: An empty line ends ``showc``.
STOP_SHOWC = EOL

#: The device closes a connection after this many seconds without traffic at the
#: prompt (measured 19.0-19.6 s; ``showc`` output counts as traffic). An empty line
#: resets the timer.
IDLE_TIMEOUT_S = 19.0

#: What the driver sends to keep an idle connection open, and how often.
KEEPALIVE = EOL
KEEPALIVE_INTERVAL_S = 8.0

DEFAULT_PORT = 23
#: The device asks for a login but accepts any user name and password; these are the
#: defaults from the PSAMPLE manual.
USER = "admin"
PASSWORD = "ccount"

#: Range of ``qrate n`` in the help text; the report period is n x 100 ms. The device
#: raises 0 to 1 but accepts anything above 100, so the driver checks the range.
QRATE_MIN = 1
QRATE_MAX = 100

#: The prompt the device shows when it waits for a command.
PROMPT = b">"

#: Login prompts, without line endings.
USER_PROMPT = b"Username: "
PASSWORD_PROMPT = b"Password: "

###############################################################################
# Commands                                                                    #
###############################################################################


def command(name: str, *args: object) -> bytes:
    """Encode a command line, such as ``command("qrate", 10)`` -> ``b"qrate 10\\r\\n"``."""
    text = " ".join([name, *(str(a) for a in args)])
    return text.encode("ascii") + EOL


def qrate_command(n: int) -> bytes:
    """Encode ``qrate n``, checking that n is in the documented range."""
    if not QRATE_MIN <= n <= QRATE_MAX:
        raise ValueError(f"qrate must be between {QRATE_MIN} and {QRATE_MAX}, not {n}")
    return command("qrate", n)


def qrate_period_s(n: int) -> float:
    """Report period (and counting window) of ``qrate n`` in seconds."""
    return n * 0.1


###############################################################################
# Lines                                                                       #
###############################################################################


def split_lines(buffer: bytes) -> tuple[list[bytes], bytes]:
    """Split ``buffer`` into complete ``\\r\\n`` lines and the unfinished rest."""
    *lines, rest = buffer.split(EOL)
    return lines, rest


#: ANSI escape sequences, such as the clear-screen and colour codes in the banner.
_ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def decode(line: bytes) -> str:
    """Decode a line from the device, without ANSI escape codes and surrounding blanks."""
    return _ANSI_ESCAPE.sub("", line.decode("latin-1")).strip()


def ends_with_prompt(buffer: bytes) -> bool:
    """Return True if the device is waiting for a command (the buffer ends in ``> ``)."""
    return buffer.rstrip(b" ").endswith(PROMPT)


###############################################################################
# Replies                                                                     #
###############################################################################

_SAMPLE_LINE = re.compile(r"^\[(\d+)\]\s+(.*)$")


def parse_sample(line: str, t_wall: float = 0.0, t_mono: float = 0.0) -> Sample | None:
    """Parse one ``showc`` or ``show`` line such as ``[767] 5 57 0 0.0 0.0``.

    Returns ``None`` for anything else. A line needs the ``[n]`` counter and at least
    as many numbers as :data:`FIELD_ORDER` names.
    """
    match = _SAMPLE_LINE.match(line.strip())
    if match is None:
        return None
    try:
        values = [_number(token) for token in match.group(2).split()]
    except ValueError:
        return None
    if len(values) < len(FIELD_ORDER):
        return None
    named = dict(zip(FIELD_ORDER, values))
    return Sample(index=int(match.group(1)), raw_extra=tuple(values[len(FIELD_ORDER):]), raw=line.strip(),
                  t_wall=t_wall, t_mono=t_mono, **named)


_COUNTER_LINE = re.compile(r"^Counter\s+(\d+)\s*=\s*(\S+)$")


def parse_counters(reply: str, t_wall: float = 0.0, t_mono: float = 0.0) -> Sample | None:
    """Parse a ``ccnt`` reply: `` Counter 1 = 8``, `` Counter 2 = 84``, `` Counter 3 = 0``.

    The reply has no ``[n]``, so the sample's index is -1. Returns ``None`` unless
    every counter that :data:`FIELD_ORDER` names is there.
    """
    counters = {}
    for line in reply.splitlines():
        match = _COUNTER_LINE.match(line.strip())
        if match is not None:
            try:
                counters[int(match.group(1))] = _number(match.group(2))
            except ValueError:
                return None
    if not all(k in counters for k in range(1, len(FIELD_ORDER) + 1)):
        return None
    named = {name: counters[k] for k, name in enumerate(FIELD_ORDER, start=1)}
    return Sample(index=-1, raw=reply.strip(), t_wall=t_wall, t_mono=t_mono, **named)


_QRATE_REPLY = re.compile(r"qrate = (\d+)")


def parse_qrate_reply(reply: str) -> int | None:
    """Parse the reply of ``grate``: ``qrate = 10``."""
    match = _QRATE_REPLY.search(reply)
    return int(match.group(1)) if match else None


def _number(token: str) -> float:
    """Parse an integer as ``int`` and anything else as ``float``."""
    try:
        return int(token)
    except ValueError:
        return float(token)
