"""The simulator's command line starts a server the driver can use."""

import socket
import subprocess
import sys
import time

import pytest

from twilite import TwiliteClient


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.mark.simulator_only
def test_python_m_twilite_sim():
    port = free_port()
    process = subprocess.Popen(
        [sys.executable, "-m", "twilite.sim", "--port", str(port), "--scenario", "bolus", "--isotope", "Ga-68",
         "--idle-timeout", "0"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    try:
        deadline = time.monotonic() + 10
        while True:
            try:
                client = TwiliteClient("127.0.0.1", port, timeout=2)
                client.connect()
                break
            except Exception:
                if time.monotonic() > deadline or process.poll() is not None:
                    raise
                time.sleep(0.2)
        client.set_query_rate(1)
        sample = next(client.stream())
        client.request_stop()
        client.stop()
        client.close()
        assert len(sample.raw_extra) == 2
    finally:
        process.terminate()
        process.wait(5)


def test_help():
    result = subprocess.run([sys.executable, "-m", "twilite.sim", "--help"], capture_output=True, text=True)
    assert result.returncode == 0
    assert "--drop-after" in result.stdout and "--idle-timeout" in result.stdout
