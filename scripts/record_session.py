"""Record a raw telnet session with a twilite to answer the open protocol questions.

Uses a bare socket, not the driver, so no assumption of the driver can hide what the
device does. Every byte in both directions is written to the log with a timestamp, in
the driver's raw-log format, so the file can go straight into
``tests/fixtures/transcripts`` and the simulator's ``replay`` scenario.

    uv run python scripts/record_session.py 10.0.52.25
    uv run python scripts/record_session.py 127.0.0.1 --port 2323   # against the simulator

What it does, with a pause after each step to collect the reply:
connect and wait for the banner (logging in with admin/ccount if asked); help; ?;
ccnt; show; qrate 10; showc for 15 s, then one candidate after another to stop it
(empty line, "q", Ctrl+C) until the prompt comes back; qrate 50 and showc again to
time the period; rinfo; adc; bye.
"""

from __future__ import annotations

import argparse
import re
import socket
import time
from datetime import datetime
from pathlib import Path

STOP_CANDIDATES = [b"\r\n", b"q\r\n", b"\x03"]


class Recorder:
    def __init__(self, host: str, port: int, log_path: Path):
        self.sock = socket.create_connection((host, port), timeout=10)
        self.sock.settimeout(0.1)
        self.log = open(log_path, "a", encoding="utf-8")
        self.received = b""
        self.note(f"connect {host}:{port}")

    def note(self, text: str) -> None:
        self._write("--", text.encode())
        print(f"\n-- {text}")

    def _write(self, direction: str, data: bytes) -> None:
        self.log.write(f"{datetime.now().isoformat(timespec='milliseconds')} {direction} {data!r}\n")
        self.log.flush()

    def send(self, data: bytes) -> None:
        self._write(">>", data)
        print(f">> {data!r}")
        self.sock.sendall(data)

    def read_for(self, seconds: float) -> bytes:
        """Collect everything that arrives within ``seconds``; print it as it comes."""
        out = b""
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            try:
                data = self.sock.recv(4096)
            except TimeoutError:
                continue
            if not data:
                self.note("connection closed by the device")
                break
            self._write("<<", data)
            print(data.decode("latin-1"), end="", flush=True)
            out += data
        self.received += out
        return out

    def command(self, line: str, seconds: float = 2.0) -> bytes:
        self.note(f"command {line!r}")
        self.send(line.encode("ascii") + b"\r\n")
        return self.read_for(seconds)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("host")
    parser.add_argument("--port", type=int, default=23)
    parser.add_argument("--user", default="admin")
    parser.add_argument("--password", default="ccount")
    parser.add_argument("--out", type=Path, help="log file (default: tests/fixtures/transcripts/<time>_raw.log)")
    args = parser.parse_args()
    out = args.out or Path("tests/fixtures/transcripts") / f"{datetime.now():%Y%m%d_%H%M%S}_{args.host}_raw.log"
    out.parent.mkdir(parents=True, exist_ok=True)

    rec = Recorder(args.host, args.port, out)
    greeting = rec.read_for(3.0)
    if re.search(rb"(login|user)\s*:\s*$", greeting, re.IGNORECASE):
        rec.note("login prompt seen")
        rec.send(args.user.encode() + b"\r\n")
        rec.read_for(2.0)
        rec.send(args.password.encode() + b"\r\n")
        rec.read_for(3.0)

    for line in ("help", "?", "ccnt", "show", "qrate 10"):
        rec.command(line)

    rec.note("showc for 15 s at qrate 10")
    rec.command("showc", 15.0)
    for candidate in STOP_CANDIDATES:
        rec.note(f"trying to stop showc with {candidate!r}")
        rec.send(candidate)
        after = rec.read_for(3.0)
        if after.rstrip().endswith(b">") and not re.search(rb"\[\d+\][^\r\n]*\r?\n?$", after[-80:]):
            rec.note(f"prompt back after {candidate!r}")
            break
    else:
        rec.note("showc did not stop with any candidate")

    rec.command("qrate 50")
    rec.note("showc for 12 s at qrate 50 (is the period 5 s or 50 s?)")
    rec.command("showc", 12.0)
    rec.send(STOP_CANDIDATES[0])
    rec.read_for(3.0)

    for line in ("rinfo", "adc"):
        rec.command(line)
    rec.command("bye", 2.0)
    rec.note("done")
    print(f"\nSession written to {out}")


if __name__ == "__main__":
    main()
