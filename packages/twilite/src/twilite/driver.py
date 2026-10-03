"""Blocking client for one telnet connection to a twilite (or the simulator)."""

from __future__ import annotations

import logging
import socket
import threading
import time
from collections.abc import Callable, Iterator
from datetime import datetime
from pathlib import Path

from twilite import protocol
from twilite.sample import Sample

log = logging.getLogger(__name__)

#: How often a blocking read wakes up to check for a stop request, in seconds.
POLL_INTERVAL_S = 0.1


class TwiliteError(Exception):
    """Base class of the driver's errors."""


class ConnectionLost(TwiliteError):
    """The socket closed, failed, or stayed silent for longer than the timeout."""


class TwiliteClient:
    """One telnet connection to a twilite.

    The client is blocking and meant to be used from a single thread at a time; only
    :meth:`request_stop` may be called from another thread. It never reconnects by
    itself: after :class:`ConnectionLost`, the caller decides what to do.

    Args:
        host: IP address or host name.
        port: TCP port, 23 on the device.
        timeout: Seconds to wait for the device before raising
            :class:`ConnectionLost`. While streaming, the wait also allows two report
            periods.
        raw_log: File that every byte sent and received is appended to, with a
            timestamp, or ``None``.
    """

    def __init__(self, host: str, port: int = protocol.DEFAULT_PORT, timeout: float = 5.0,
                 raw_log: str | Path | None = None):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.raw_log_path = Path(raw_log) if raw_log else None
        self.banner = ""
        self.report_period_s = 1.0
        self._sock: socket.socket | None = None
        self._buffer = b""
        self._raw_log = None
        self._streaming = False
        self._stop_requested = threading.Event()
        self._last_traffic = time.monotonic()

    ###########################################################################
    # Connection                                                              #
    ###########################################################################

    @property
    def connected(self) -> bool:
        return self._sock is not None

    @property
    def streaming(self) -> bool:
        return self._streaming

    @property
    def idle_s(self) -> float:
        """Seconds since anything was sent or received."""
        return time.monotonic() - self._last_traffic

    def connect(self) -> str:
        """Open the connection, log in, wait for the prompt; return the banner."""
        if self._sock is not None:
            raise TwiliteError("Already connected")
        if self.raw_log_path is not None:
            self.raw_log_path.parent.mkdir(parents=True, exist_ok=True)
            self._raw_log = open(self.raw_log_path, "ab")
        self._log_raw("--", f"connect {self.host}:{self.port}".encode())
        try:
            self._sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        except OSError as error:
            self._close_log()
            raise ConnectionLost(f"Cannot connect to {self.host}:{self.port}: {error}") from error
        self._sock.settimeout(POLL_INTERVAL_S)
        self._buffer = b""
        try:
            self.banner = self._login()
        except Exception:
            self._close_socket()
            raise
        log.info("Connected to %s:%s (%s)", self.host, self.port, self.banner or "no banner")
        return self.banner

    def _login(self) -> str:
        """Answer ``Username:`` and ``Password:``; return the banner printed around them."""
        deadline = time.monotonic() + self.timeout
        self._read_until(lambda buf: buf.endswith(protocol.USER_PROMPT), deadline)
        greeting = self._buffer[:-len(protocol.USER_PROMPT)]
        self._buffer = b""
        self._send(protocol.USER.encode("ascii") + protocol.EOL)
        self._read_until(lambda buf: buf.endswith(protocol.PASSWORD_PROMPT), deadline)
        self._buffer = b""
        self._send(protocol.PASSWORD.encode("ascii") + protocol.EOL)
        self._read_until(protocol.ends_with_prompt, deadline)
        greeting += self._buffer[:self._buffer.rstrip().rfind(protocol.PROMPT)]
        self._buffer = b""
        lines, rest = protocol.split_lines(greeting)
        return "\n".join(text for text in (protocol.decode(line) for line in [*lines, rest]) if text)

    def close(self) -> None:
        """Stop the stream if it runs, say ``bye`` and close the socket. Never raises."""
        if self._sock is not None:
            try:
                if self._streaming:
                    self.stop()
                self._send(protocol.command("bye"))
            except TwiliteError:
                pass
        self._close_socket()

    def __enter__(self) -> TwiliteClient:
        self.connect()
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    ###########################################################################
    # Commands                                                                #
    ###########################################################################

    def command(self, name: str, *args: object) -> str:
        """Send a command and return its reply, without the prompt."""
        return self._command(protocol.command(name, *args))

    def set_query_rate(self, n: int) -> str:
        """Report every n x 100 ms (``qrate n``, 1 <= n <= 100)."""
        reply = self._command(protocol.qrate_command(n))
        self.report_period_s = protocol.qrate_period_s(n)
        return reply

    def read_query_rate(self) -> int | None:
        """Read the device's ``qrate`` (``grate``, V3.00); ``None`` if the reply does not parse."""
        return protocol.parse_qrate_reply(self.command("grate"))

    def read_counters(self) -> Sample | None:
        """Read the counters once (``ccnt``, index -1); ``None`` if the reply does not parse."""
        reply = self.command("ccnt")
        sample = protocol.parse_counters(reply, time.time(), time.monotonic())
        if sample is None:
            log.warning("ccnt reply did not parse: %r", reply)
        return sample

    def keepalive(self) -> None:
        """Send an empty line and wait for the prompt, so the device keeps the connection.

        The device closes a connection that stays silent for
        :data:`~twilite.protocol.IDLE_TIMEOUT_S` at the prompt. Call this at least every
        :data:`~twilite.protocol.KEEPALIVE_INTERVAL_S` while connected but not streaming.

        Raises:
            ConnectionLost: The device already closed the connection.
        """
        self._command(protocol.KEEPALIVE)

    def _command(self, line: bytes) -> str:
        if self._streaming:
            raise TwiliteError("Stop the stream before sending another command")
        self._require_connection()
        self._buffer = b""
        self._send(line)
        self._read_until(protocol.ends_with_prompt, time.monotonic() + self.timeout)
        reply, self._buffer = self._buffer, b""
        reply = reply[:reply.rstrip().rfind(protocol.PROMPT)]
        lines, rest = protocol.split_lines(reply)
        return "\n".join(text for text in (protocol.decode(l) for l in [*lines, rest]) if text)

    ###########################################################################
    # Streaming                                                               #
    ###########################################################################

    def stream(self) -> Iterator[Sample]:
        """Send ``showc`` and yield every sample until :meth:`request_stop`.

        Lines that do not parse are logged and skipped. ``[n]`` should go up by one per
        line; anything else is logged, and the samples are yielded all the same. A stop
        requested before the stream starts ends it at once; the request is cleared
        when the stream ends.

        Raises:
            ConnectionLost: The socket closed or nothing arrived within the timeout.
        """
        self._require_connection()
        if self._streaming:
            raise TwiliteError("Already streaming")
        self._buffer = b""
        self._send(protocol.command("showc"))
        self._streaming = True
        silence_limit = self.timeout + 2 * self.report_period_s
        last_data = time.monotonic()
        previous = None
        try:
            while not self._stop_requested.is_set():
                lines, self._buffer = protocol.split_lines(self._buffer)
                for raw_line in lines:
                    sample = self._parse_stream_line(raw_line)
                    if sample is None:
                        continue
                    if previous is not None and sample.index != previous + 1:
                        log.warning("Sample counter went from [%d] to [%d]", previous, sample.index)
                    previous = sample.index
                    yield sample
                    if self._stop_requested.is_set():
                        break
                if self._stop_requested.is_set():
                    break
                if self._receive():
                    last_data = time.monotonic()
                elif time.monotonic() - last_data > silence_limit:
                    self._close_socket()
                    raise ConnectionLost(f"No data from {self.host} for {silence_limit:.1f} s")
        finally:
            # A generator closed by `break` in the caller lands here too; the caller
            # then calls stop(), which needs to know the stream is still running.
            try:
                if self._stop_requested.is_set() and self._sock is not None:
                    self.stop()
            finally:
                self._stop_requested.clear()

    def _parse_stream_line(self, raw_line: bytes) -> Sample | None:
        text = protocol.decode(raw_line)
        if not text or text == ">":
            return None
        sample = protocol.parse_sample(text, time.time(), time.monotonic())
        if sample is None:
            log.warning("Skipped a line that does not parse: %r", text)
        return sample

    def request_stop(self) -> None:
        """Ask a running :meth:`stream` to stop; safe to call from any thread."""
        self._stop_requested.set()

    def stop(self) -> None:
        """End ``showc`` and wait for the prompt. Call it from the streaming thread."""
        if not self._streaming:
            return
        self._streaming = False
        if self._sock is None:
            return
        self._send(protocol.STOP_SHOWC)
        try:
            self._read_until(protocol.ends_with_prompt, time.monotonic() + self.timeout)
        finally:
            self._buffer = b""

    ###########################################################################
    # Socket I/O                                                              #
    ###########################################################################

    def _require_connection(self) -> None:
        if self._sock is None:
            raise ConnectionLost("Not connected")

    def _send(self, data: bytes) -> None:
        self._require_connection()
        self._log_raw(">>", data)
        self._last_traffic = time.monotonic()
        try:
            self._sock.sendall(data)
        except OSError as error:
            self._close_socket()
            raise ConnectionLost(f"Send failed: {error}") from error

    def _receive(self) -> bool:
        """Read what is there within one poll interval; return True if data came."""
        self._require_connection()
        try:
            data = self._sock.recv(4096)
        except TimeoutError:
            return False
        except OSError as error:
            self._close_socket()
            raise ConnectionLost(f"Receive failed: {error}") from error
        if not data:
            self._close_socket()
            raise ConnectionLost("The device closed the connection")
        self._log_raw("<<", data)
        self._last_traffic = time.monotonic()
        self._buffer += data
        return True

    def _read_until(self, predicate: Callable[[bytes], bool], deadline: float) -> None:
        while not predicate(self._buffer):
            if time.monotonic() > deadline:
                received = protocol.decode(self._buffer[-80:])
                self._close_socket()
                raise ConnectionLost(f"Timed out waiting for the device (last received: {received!r})")
            self._receive()

    def _close_socket(self) -> None:
        self._streaming = False
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
            self._log_raw("--", b"closed")
        self._close_log()

    def _log_raw(self, direction: str, data: bytes) -> None:
        if self._raw_log is None:
            return
        stamp = datetime.now().isoformat(timespec="milliseconds")
        self._raw_log.write(f"{stamp} {direction} {data!r}\n".encode())
        self._raw_log.flush()

    def _close_log(self) -> None:
        if self._raw_log is not None:
            self._raw_log.close()
            self._raw_log = None
