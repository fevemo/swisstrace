import pytest

from twilite import protocol
from twilite.protocol import parse_sample, split_lines


class TestParseSample:
    def test_device_lines(self):
        # Recorded on Coincident Counter V3.00.
        first = parse_sample("[1474] 119000 117060 116500 0.0 0.0")
        second = parse_sample("[767] 5 57 0 0.0 0.0")
        assert (first.index, first.singles1, first.singles2, first.coincidences) == (1474, 119000, 117060, 116500)
        assert first.raw_extra == (0.0, 0.0)
        assert (second.index, second.coincidences) == (767, 0)

    def test_line_without_analog_fields(self):
        sample = parse_sample("[3] 10 20 30")
        assert sample.raw_extra == ()
        assert sample.coincidences == 30

    def test_surrounding_spaces(self):
        sample = parse_sample("  [5]  1 2 3  ")
        assert sample.index == 5 and sample.singles1 == 1

    def test_keeps_times_and_raw_line(self):
        sample = parse_sample("[1] 1 2 3", t_wall=100.0, t_mono=5.0)
        assert (sample.raw, sample.t_wall, sample.t_mono) == ("[1] 1 2 3", 100.0, 5.0)

    def test_integers_stay_integers_and_decimals_are_floats(self):
        sample = parse_sample("[1] 1 2.5 3")
        assert isinstance(sample.singles1, int) and sample.singles2 == 2.5

    @pytest.mark.parametrize("line", [
        "", ">", "showc", "Coincident Counter", "[71]", "[71] 1 2", "[x] 1 2 3", "71 1 2 3",
        "[71] 1 two 3", "Error: Unknown command. Use help or ? to show help screen.", "Counter 1 = 8",
    ])
    def test_malformed_lines_give_none(self, line):
        assert parse_sample(line) is None

    def test_field_order_is_one_table(self, monkeypatch):
        monkeypatch.setattr(protocol, "FIELD_ORDER", ("coincidences", "singles1", "singles2"))
        sample = parse_sample("[1] 124 2152 1576")
        assert (sample.coincidences, sample.singles1, sample.singles2) == (124, 2152, 1576)


class TestSplitLines:
    def test_crlf_lines_and_rest(self):
        lines, rest = split_lines(b"a\r\n\r\nb\r\n> ")
        assert lines == [b"a", b"", b"b"]
        assert rest == b"> "

    def test_trailing_cr_waits_for_its_lf(self):
        lines, rest = split_lines(b"a\r")
        assert lines == [] and rest == b"a\r"
        lines, rest = split_lines(rest + b"\nb")
        assert lines == [b"a"] and rest == b"b"

    def test_line_split_across_packets(self):
        stream = b"[71] 2152 1576 124 0.0 0.0\r\n[72] 2218 1497 122 0.0 0.0\r\n"
        for cut in range(1, len(stream)):
            buffer, found = b"", []
            for packet in (stream[:cut], stream[cut:]):
                lines, buffer = split_lines(buffer + packet)
                found += lines
            assert [parse_sample(line.decode()).index for line in found] == [71, 72], cut


class TestCommands:
    def test_command_encoding(self):
        assert protocol.command("showc") == b"showc\r\n"
        assert protocol.qrate_command(10) == b"qrate 10\r\n"

    @pytest.mark.parametrize("n", [0, 101, -1])
    def test_qrate_range(self, n):
        with pytest.raises(ValueError):
            protocol.qrate_command(n)

    def test_qrate_period(self):
        assert protocol.qrate_period_s(10) == pytest.approx(1.0)
        assert protocol.qrate_period_s(1) == pytest.approx(0.1)

    @pytest.mark.parametrize("text, expected", [
        (b"x\r\n> ", True), (b">", True), (b"[1] 1 2 3", False), (b"login: ", False),
    ])
    def test_prompt(self, text, expected):
        assert protocol.ends_with_prompt(text) is expected


class TestCounters:
    def test_v300_ccnt_reply(self):
        # Recorded on Coincident Counter V3.00: Counter 1/2/3 = singles 1, singles 2, coincidences.
        sample = protocol.parse_counters(" Counter 1 = 8\r\n Counter 2 = 84\r\n Counter 3 = 0\r\n")
        assert (sample.index, sample.singles1, sample.singles2, sample.coincidences) == (-1, 8, 84, 0)

    def test_missing_counter(self):
        assert protocol.parse_counters("Counter 1 = 8\nCounter 2 = 84") is None

    def test_report_line_is_not_a_counter_reply(self):
        assert protocol.parse_counters("[767] 5 57 0 0.0 0.0") is None

    def test_grate_reply(self):
        assert protocol.parse_qrate_reply("qrate = 10") == 10
        assert protocol.parse_qrate_reply("Error: Unknown command.") is None


class TestDecode:
    def test_banner_line_loses_ansi_codes(self):
        # Recorded on Coincident Counter V3.00.
        line = b"\x1b[0m        \x1b[37;44m*            Coincident Counter                               *"
        assert protocol.decode(line) == "*            Coincident Counter                               *"

    def test_clear_screen_alone_is_empty(self):
        assert protocol.decode(b"\x1b[2J") == ""
