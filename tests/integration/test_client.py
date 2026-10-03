"""TwiliteClient against the simulator (both profiles), or a real device with --hardware."""

import time

import pytest

from twilite import ConnectionLost, TwiliteClient, TwiliteError, protocol
from twilite.sim import Faults
from twilite.storage import AcquisitionWriter, read_acquisition


def client_for(target, **kwargs) -> TwiliteClient:
    kwargs.setdefault("timeout", 3.0)
    return TwiliteClient(target.host, target.port, **kwargs)


def take(client, n, **kwargs):
    """Stream n samples, then stop; return them."""
    out = []
    for sample in client.stream(**kwargs):
        out.append(sample)
        if len(out) == n:
            client.request_stop()
    return out


class TestSession:
    def test_connect_reads_banner_and_closes(self, target):
        client = client_for(target)
        banner = client.connect()
        assert client.connected
        assert banner.splitlines()[0] == "Coincident Counter - Telnet Server V3.00, please login..."
        client.close()
        assert not client.connected

    def test_context_manager(self, target):
        with client_for(target) as client:
            assert client.connected
        assert not client.connected

    def test_qrate_is_sent(self, target):
        with client_for(target) as client:
            client.set_query_rate(5)
            assert client.report_period_s == pytest.approx(0.5)
        if not target.is_hardware:
            assert "qrate 5" in target.simulator.commands_received
            assert target.simulator.qrate == 5

    def test_qrate_out_of_range_is_not_sent(self, target):
        with client_for(target) as client:
            with pytest.raises(ValueError):
                client.set_query_rate(0)
            assert client.command("help")  # the session is still usable

    def test_read_counters_once(self, target):
        with client_for(target) as client:
            sample = client.read_counters()
            assert sample is not None and sample.coincidences >= 0

    def test_device_replies(self, target):
        with client_for(target) as client:
            assert client.read_counters().index == -1  # Counter k = v, no [n]
            assert client.set_query_rate(7) == ""  # qrate prints nothing
            assert client.read_query_rate() == 7
            client.set_query_rate(10)
            assert "Unknown command" in client.command("nonsense")

    def test_help_lists_showc(self, target):
        with client_for(target) as client:
            assert "showc" in client.command("help")


class TestStreaming:
    def test_stream_start_stop_and_command_after(self, target):
        with client_for(target) as client:
            client.set_query_rate(1)
            samples = take(client, 5)
            assert len(samples) == 5
            assert not client.streaming
            # The prompt is back: a command works straight after the stream.
            assert "showc" in client.command("help")

    def test_indices_increase_without_repeats(self, target):
        with client_for(target) as client:
            client.set_query_rate(1)
            indices = [s.index for s in take(client, 6)]
        assert indices == list(range(indices[0], indices[0] + 6))  # one [n] per line

    def test_samples_have_both_clocks(self, target):
        before = time.time()
        with client_for(target) as client:
            client.set_query_rate(1)
            samples = take(client, 3)
        assert all(before <= s.t_wall <= time.time() for s in samples)
        assert samples[0].t_mono < samples[-1].t_mono

    def test_break_then_stop(self, target):
        with client_for(target) as client:
            client.set_query_rate(1)
            for sample in client.stream():
                break
            client.stop()
            assert client.command("help")

    def test_command_while_streaming_is_refused(self, target):
        with client_for(target) as client:
            client.set_query_rate(1)
            stream = client.stream()
            next(stream)
            with pytest.raises(TwiliteError):
                client.command("help")
            client.request_stop()
            for _ in stream:
                pass

    def test_request_stop_from_another_thread(self, target):
        import threading

        with client_for(target) as client:
            client.set_query_rate(1)
            threading.Timer(0.5, client.request_stop).start()
            started = time.monotonic()
            samples = list(client.stream())
            assert time.monotonic() - started < 2.0
            assert samples

    def test_stop_requested_before_the_stream_starts(self, target):
        # A Stop clicked right after Start must not be lost.
        with client_for(target) as client:
            client.set_query_rate(1)
            client.request_stop()
            started = time.monotonic()
            assert list(client.stream()) == []
            assert time.monotonic() - started < 2.0
            # The request ended that stream only: the next one runs.
            assert len(take(client, 2)) == 2

    def test_full_acquisition_to_disk(self, target, tmp_path):
        with client_for(target, raw_log=tmp_path / "raw.log") as client:
            client.set_query_rate(1)
            writer = AcquisitionWriter(tmp_path, {"device": f"{target.host}:{target.port}", "banner": client.banner})
            for sample in take(client, 8):
                writer.write_sample(sample)
            path = writer.finish()
        acq = read_acquisition(path)
        assert len(acq) == 8
        assert acq.t_rel_s == sorted(acq.t_rel_s)
        raw = (tmp_path / "raw.log").read_text()
        assert "showc" in raw and ">>" in raw and "<<" in raw


class TestLogin:
    def test_any_credentials_are_accepted(self, target, monkeypatch):
        # The device asks for a login but checks nothing.
        monkeypatch.setattr(protocol, "USER", "nobody")
        monkeypatch.setattr(protocol, "PASSWORD", "wrong")
        with client_for(target) as client:
            assert client.read_query_rate() is not None


class TestConnectionErrors:
    def test_nothing_listening(self, simulator_factory):
        sim = simulator_factory()
        port = sim.port
        sim.stop()
        with pytest.raises(ConnectionLost):
            TwiliteClient("127.0.0.1", port, timeout=1).connect()

    def test_reconnect_keeps_device_counter(self, simulator_factory):
        sim = simulator_factory()
        with TwiliteClient("127.0.0.1", sim.port, timeout=2) as client:
            client.set_query_rate(1)
            first = take(client, 2)
        with TwiliteClient("127.0.0.1", sim.port, timeout=2) as client:
            second = take(client, 2)
        assert second[0].index == first[-1].index + 1  # [n] continues across connections


@pytest.mark.simulator_only
class TestIdleTimeout:
    """The device closes a connection that stays idle at the prompt (about 19 s)."""

    def test_idle_connection_is_closed(self, simulator_factory):
        sim = simulator_factory(idle_timeout_s=0.3)
        with TwiliteClient("127.0.0.1", sim.port, timeout=1) as client:
            time.sleep(0.6)
            with pytest.raises(ConnectionLost):
                client.keepalive()
            assert not client.connected

    def test_keepalive_keeps_it_open(self, simulator_factory):
        sim = simulator_factory(idle_timeout_s=0.3)
        with TwiliteClient("127.0.0.1", sim.port, timeout=1) as client:
            for _ in range(8):
                time.sleep(0.1)
                client.keepalive()
            assert client.idle_s < 0.1
            assert "showc" in client.command("help")
            assert sim.connection_count == 1

    def test_streaming_is_not_idle(self, simulator_factory):
        sim = simulator_factory(idle_timeout_s=0.3)
        with TwiliteClient("127.0.0.1", sim.port, timeout=1) as client:
            client.set_query_rate(1)
            assert len(take(client, 8)) == 8  # about 0.8 s, longer than the idle timeout
            client.keepalive()


@pytest.mark.simulator_only
class TestFaults:
    def connect(self, sim, timeout=2.0):
        client = TwiliteClient("127.0.0.1", sim.port, timeout=timeout)
        client.connect()
        client.set_query_rate(1)
        return client

    def test_drop_after_n_lines(self, simulator_factory):
        sim = simulator_factory(faults=Faults(drop_after=6))
        client = self.connect(sim)
        received = []
        with pytest.raises(ConnectionLost):
            for sample in client.stream():
                received.append(sample)
        assert 1 <= len(received) <= 6
        assert not client.connected

    def test_cable_pull_mid_stream(self, simulator_factory):
        sim = simulator_factory()
        client = self.connect(sim)
        with pytest.raises(ConnectionLost):
            for sample in client.stream():
                sim.drop_connections()

    def test_stall_times_out_within_its_limit(self, simulator_factory):
        sim = simulator_factory(faults=Faults(stall_after=3, stall_s=10))
        client = self.connect(sim, timeout=1.0)
        last = None
        with pytest.raises(ConnectionLost):
            for _ in client.stream():
                last = time.monotonic()
        waited = time.monotonic() - last
        # Limit: timeout + two report periods = 1.2 s.
        assert 1.0 <= waited < 2.0

    def test_counter_jump_is_logged_and_kept(self, simulator_factory, tmp_path, caplog):
        transcript = tmp_path / "jump.txt"
        transcript.write_text("[1] 1 2 3 0.0 0.0\n[2] 1 2 3 0.0 0.0\n[5] 1 2 3 0.0 0.0\n[0] 1 2 3 0.0 0.0\n")
        sim = simulator_factory(scenario="replay", transcript=transcript)
        client = self.connect(sim)
        samples = take(client, 4)
        client.close()
        assert [s.index for s in samples] == [1, 2, 5, 0]
        warnings = [r.message for r in caplog.records if "Sample counter" in r.message]
        assert warnings == ["Sample counter went from [2] to [5]", "Sample counter went from [5] to [0]"]

    def test_replay_of_recorded_transcript(self, simulator_factory):
        from tests.conftest import FIXTURES

        sim = simulator_factory(scenario="replay", transcript=FIXTURES / "transcripts" / "manual_page23.txt")
        client = self.connect(sim)
        samples = take(client, 2)
        client.close()
        assert [(s.index, s.coincidences) for s in samples] == [(71, 124), (72, 122)]

    def test_replay_of_device_recording(self, simulator_factory):
        from tests.conftest import FIXTURES

        transcript = FIXTURES / "transcripts" / "2026-10-03_lab_v300_showc-qrate1.txt"
        sim = simulator_factory(scenario="replay", transcript=transcript)
        client = self.connect(sim)
        samples = take(client, 3)
        client.close()
        assert [s.index for s in samples] == [1176, 1177, 1178]
        assert (samples[0].singles1, samples[0].singles2, samples[0].coincidences) == (650, 1560, 0)
        assert samples[0].raw_extra == (0.0, 0.0)
