# Recorded transcripts

Raw sessions with a twilite, used as test fixtures and by the simulator's `replay`
scenario. Every transcript that reveals a problem gets a test that reproduces it.

- `manual_page23.txt`: the two `showc` lines printed on page 23 of the PSAMPLE manual
  (2019). Not a real recording.
- `2026-10-03_lab_v300_showc-qrate1.txt`: the driver's raw log of a session with a
  *Coincident Counter - Telnet Server V3.00*: login, `qrate 1`, 30 s of `showc` while
  the counts rise from background to about 117 000 cps, stop with Enter, then the
  device closing the idle connection (seen at the next send, 5 min later).

Add real recordings here as they arrive: PuTTY session logs (plain text) or the
driver's raw log (`TwiliteClient(raw_log=...)`, timestamped, replayed at its recorded
pace). Name them `<date>_<site or device>_<what>.txt` and note the firmware banner.
