"""Asyncio telnet server that behaves like a twilite (Coincident Counter V3.00).

Every byte it sends copies a session recorded on 2026-10-03 (see ``doc/dev/protocol.md``).
Device state (the counters and the report rate) lives in the simulator and survives
reconnects, as on the real device. Use :meth:`TwiliteSimulator.start_in_thread` to run
it next to blocking code such as tests or the GUI.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from twilite import protocol
from twilite.isotopes import Isotope, get_isotope
from twilite.sim.scenarios import Counter, Replay, make_scenario

log = logging.getLogger(__name__)

DEFAULT_PORT = 2323
#: Report rate after power-up, as qrate n. Not observed yet.
DEFAULT_QRATE = 10

_BOX_EDGE = "*" + "=" * 61 + "*"
#: Printed on connect, before ``Username: ``.
BANNER = ("\x1b[2J", "Coincident Counter - Telnet Server V3.00, please login...")
#: Printed after a good login, before the prompt.
WELCOME = (
    "\x1b[2J",
    f"        \x1b[37;44m{_BOX_EDGE}",
    "\x1b[0m        \x1b[37;44m*            Coincident Counter                               *",
    f"\x1b[0m        \x1b[37;44m{_BOX_EDGE}",
    "\x1b[0m",
)
HELP = (
    "",
    "ccnt        - shows actual counter values (single shot)",
    "show        - shows all actual values (single shot)",
    "showc       - shows all values continuously (0.1..10x/s)",
    "qrate n     - set new rate of data query (n=1..100)",
    "grate       - reads current rate of data query",
    "help, ?     - display this help",
    "bye         - disconnect",
    "",
)
UNKNOWN_COMMAND = "Error: Unknown command. Use help or ? to show help screen."
MISSING_PARAMETER = "Error: Missing parameter!"


@dataclass(slots=True)
class Faults:
    """Faults to inject, counted in report lines per connection.

    Attributes:
        drop_after: Close the connection after this many report lines.
        stall_after: Go silent for ``stall_s`` after this many report lines.
        stall_s: Length of the stall in seconds.
    """

    drop_after: int | None = None
    stall_after: int | None = None
    stall_s: float = 0.0


class _LineReader:
    """Reads command lines from the client."""

    def __init__(self, reader: asyncio.StreamReader):
        self.reader = reader
        self.buffer = b""
        self.pending: list[bytes] = []

    async def readline(self) -> str | None:
        while not self.pending:
            data = await self.reader.read(1024)
            if not data:
                return None
            self.pending, self.buffer = protocol.split_lines(self.buffer + data)
        return protocol.decode(self.pending.pop(0))


class TwiliteSimulator:
    """A simulated twilite.

    Args:
        scenario: Scenario name (see :data:`~twilite.sim.scenarios.SCENARIOS`).
        isotope: Isotope name or object for the decaying scenarios.
        host: Interface to listen on.
        port: TCP port; 0 picks a free one (read :attr:`port` after starting).
        seed: Random seed of the counts.
        faults: Faults to inject; may be changed while the simulator runs.
        transcript: Recorded session for the ``replay`` scenario.
        scenario_options: Overrides for the scenario's parameters.
        idle_timeout_s: Close a connection idle at the prompt for this long, as the
            device does after 19 s; 0 keeps it open.
    """

    def __init__(self, scenario: str = "background", isotope: str | Isotope | None = None,
                 host: str = "127.0.0.1", port: int = DEFAULT_PORT, seed: int = 1, faults: Faults | None = None,
                 transcript: str | Path | None = None, scenario_options: dict | None = None,
                 idle_timeout_s: float = protocol.IDLE_TIMEOUT_S):
        if isinstance(isotope, str):
            isotope = get_isotope(isotope)
        options = dict(scenario_options or {})
        if transcript is not None:
            options["transcript"] = Path(transcript)
        self.scenario = make_scenario(scenario, isotope, **options)
        self.faults = faults or Faults()
        self.counter = Counter(self.scenario, seed)
        self.idle_timeout_s = idle_timeout_s or None
        self.host = host
        self.port = port
        self.qrate = DEFAULT_QRATE
        self.commands_received: list[str] = []
        self.connection_count = 0
        self._t0 = time.monotonic()
        self._replay_position = 0
        self._server: asyncio.Server | None = None
        self._writers: set[asyncio.StreamWriter] = set()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None

    @property
    def elapsed_s(self) -> float:
        return time.monotonic() - self._t0

    ###########################################################################
    # Lifecycle                                                               #
    ###########################################################################

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle, self.host, self.port)
        self.port = self._server.sockets[0].getsockname()[1]
        self._t0 = time.monotonic()
        log.info("Simulated twilite (%s) on %s:%s", self.scenario.name, self.host, self.port)

    async def close(self) -> None:
        if self._server is not None:
            self._server.close()
        self._abort_all()
        if self._server is not None:
            await self._server.wait_closed()

    def start_in_thread(self) -> int:
        """Run the simulator on its own event loop thread; return the port."""
        self._loop = asyncio.new_event_loop()
        ready = threading.Event()
        errors: list[BaseException] = []

        def run() -> None:
            asyncio.set_event_loop(self._loop)
            try:
                self._loop.run_until_complete(self.start())
            except BaseException as error:  # noqa: BLE001 - reported to the caller
                errors.append(error)
                ready.set()
                return
            ready.set()
            self._loop.run_forever()
            self._loop.run_until_complete(self.close())
            self._loop.close()

        self._thread = threading.Thread(target=run, name="twilite-sim", daemon=True)
        self._thread.start()
        ready.wait(5)
        if errors:
            raise errors[0]
        return self.port

    def stop(self) -> None:
        """Stop a simulator started with :meth:`start_in_thread`."""
        if self._loop is None or self._thread is None:
            return
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(5)
        self._thread = None

    def drop_connections(self) -> None:
        """Cut every open connection, like a pulled cable (thread-safe)."""
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._abort_all)
        else:
            self._abort_all()

    def _abort_all(self) -> None:
        for writer in list(self._writers):
            writer.transport.abort()
        self._writers.clear()

    def __enter__(self) -> TwiliteSimulator:
        self.start_in_thread()
        return self

    def __exit__(self, *exc) -> None:
        self.stop()

    ###########################################################################
    # One connection                                                          #
    ###########################################################################

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self._writers.add(writer)
        self.connection_count += 1
        lines = _LineReader(reader)
        try:
            self._write_lines(writer, BANNER)
            if not await self._login(lines, writer):
                return
            while True:
                writer.write(protocol.PROMPT + b" ")
                await writer.drain()
                try:
                    line = await asyncio.wait_for(lines.readline(), self.idle_timeout_s)
                except TimeoutError:
                    log.info("Closing a connection idle for %.1f s", self.idle_timeout_s)
                    return
                if line is None or not await self._dispatch(line, lines, writer):
                    return
        except (ConnectionError, asyncio.CancelledError):
            pass
        finally:
            self._writers.discard(writer)
            if not writer.transport.is_closing():
                writer.close()

    async def _login(self, lines: _LineReader, writer: asyncio.StreamWriter) -> bool:
        """Ask for a user name and password and accept anything, as the device does."""
        for prompt in (protocol.USER_PROMPT, protocol.PASSWORD_PROMPT):
            writer.write(prompt)
            await writer.drain()
            if await lines.readline() is None:
                return False
        self._write_lines(writer, WELCOME)
        return True

    async def _dispatch(self, line: str, lines: _LineReader, writer: asyncio.StreamWriter) -> bool:
        """Run one command; return False when the connection should end."""
        if not line:
            return True
        name, *args = line.split()
        self.commands_received.append(line)
        if name in ("help", "?"):
            self._write_lines(writer, HELP)
        elif name == "bye":
            return False
        elif name == "qrate":
            if not args or not args[0].isdigit():
                self._write_lines(writer, [MISSING_PARAMETER])
            else:
                self.qrate = max(int(args[0]), protocol.QRATE_MIN)  # 0 becomes 1, no upper limit
        elif name == "grate":
            self._write_lines(writer, [f"qrate = {self.qrate}"])
        elif name == "ccnt":
            self._count(advance=False)
            self._write_lines(writer, [f" Counter {k} = {v}" for k, v in enumerate(self.counter.values, start=1)])
        elif name == "show":
            self._count()
            self._write_lines(writer, [self.counter.line()])
        elif name == "showc":
            return await self._showc(lines, writer)
        else:
            self._write_lines(writer, [UNKNOWN_COMMAND])
        return True

    def _count(self, advance: bool = True) -> None:
        self.counter.report(self.elapsed_s, protocol.qrate_period_s(self.qrate), advance)

    async def _showc(self, lines: _LineReader, writer: asyncio.StreamWriter) -> bool:
        """Report until the client sends any line; return False if the connection ended."""
        emitter = asyncio.create_task(self._emit(writer))
        waiter = asyncio.create_task(lines.readline())
        done, _ = await asyncio.wait({emitter, waiter}, return_when=asyncio.FIRST_COMPLETED)
        if waiter in done:
            emitter.cancel()
            try:
                await emitter
            except asyncio.CancelledError:
                pass
            return waiter.result() is not None
        waiter.cancel()
        return False

    async def _emit(self, writer: asyncio.StreamWriter) -> None:
        faults = self.faults
        sent = 0
        # Report on a fixed clock, as the device does: sleeping a whole period after each
        # line would add the loop's own time to every period and drift on a busy machine.
        loop = asyncio.get_running_loop()
        deadline = loop.time()
        while True:
            line = self._next_report_line()
            if line is None:  # replay finished: stay silent
                await asyncio.sleep(3600)
                continue
            sent += 1
            if faults.drop_after is not None and sent > faults.drop_after:
                writer.transport.abort()
                return
            if faults.stall_after is not None and sent == faults.stall_after + 1:
                await asyncio.sleep(faults.stall_s)
                deadline = loop.time()
            self._write_lines(writer, [line])
            await writer.drain()
            delay = self._report_delay()
            deadline += delay
            now = loop.time()
            if deadline < now - delay:
                deadline = now  # more than a period behind: carry on from now, no burst
            await asyncio.sleep(max(0.0, deadline - now))

    def _next_report_line(self) -> str | None:
        if isinstance(self.scenario, Replay):
            if self._replay_position >= len(self.scenario.lines):
                return None
            line = self.scenario.lines[self._replay_position]
            self._replay_position += 1
            return line
        self._count()
        return self.counter.line()

    def _report_delay(self) -> float:
        if isinstance(self.scenario, Replay):
            position = self._replay_position
            if position < len(self.scenario.delays_s) and self.scenario.delays_s[position] is not None:
                return self.scenario.delays_s[position]
        return protocol.qrate_period_s(self.qrate)

    @staticmethod
    def _write_lines(writer: asyncio.StreamWriter, lines) -> None:
        writer.write(b"".join(text.encode("latin-1") + protocol.EOL for text in lines))
