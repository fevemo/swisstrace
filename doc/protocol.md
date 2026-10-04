# Twilite telnet protocol, as observed

What a *Coincident Counter - Telnet Server V3.00* sent and accepted on 2026-10-03,
from the app's raw logs and short probes. The driver and the simulator implement
exactly this and nothing else. Older firmware, such as the *SwissTrace BLOOD SAMPLER*
console shown in the PMOD *PSAMPLE* manual (2019), is not supported: if one turns up,
record a session with `scripts/record_session.py <ip>` and add what differs.

## Connection

- Plain TCP on port 23. The device sends no telnet option negotiation (no IAC byte in
  any session) and does not echo commands.
- Every line ends in `\r\n` in both directions. Prompts have no line ending.
- On connect: `ESC[2J\r\nCoincident Counter - Telnet Server V3.00, please login...\r\nUsername: `,
  then `Password: `.
- **The login checks nothing:** any user name and password, empty included, get in.
  The driver sends the manual's `admin` / `ccount`.
- After the login: `ESC[2J`, a three-line box around *Coincident Counter* in ANSI
  colours (`ESC[37;44m` ... `ESC[0m`), an empty line, then the prompt `> `. The
  driver strips the ANSI codes from the banner.
- **Idle timeout:** the device closes the connection after 19.0-19.6 s without traffic
  at the prompt. An empty line resets the timer; `showc` output counts as traffic.
  Between commands the app sends an empty line after 8 s of idle time
  (`TwiliteClient.keepalive`). A script that keeps a connection open must do the same.

## Commands

The `help` screen, verbatim (between two empty lines):

```
ccnt        - shows actual counter values (single shot)
show        - shows all actual values (single shot)
showc       - shows all values continuously (0.1..10x/s)
qrate n     - set new rate of data query (n=1..100)
grate       - reads current rate of data query
help, ?     - display this help
bye         - disconnect
```

Replies:

- `ccnt`: ` Counter 1 = 8\r\n Counter 2 = 84\r\n Counter 3 = 0` (note the leading
  space), in the same order as a report line. It has no `[n]` and does not advance it.
- `show`: one report line; it advances `[n]`.
- `showc`: report lines until the client sends an empty line, then `> `. One more
  report line may arrive after the empty line. Nothing is printed while the PMTs are
  off (green play button on the touch screen not pressed).
- `qrate n`: just the prompt. The device raises 0 to 1 but accepts anything above 100
  (`qrate 500` reads back as 500); the driver refuses n outside 1-100.
- `qrate` without a number: `Error: Missing parameter!`
- `grate`: `qrate = 10`.
- Unknown command: `Error: Unknown command. Use help or ? to show help screen.`
- `bye`: closes the connection without a word.

## Report lines

```
[767] 5 57 0 0.0 0.0
```

`[n] singles1 singles2 coincidences 0.0 0.0`, checked with a source at one detector.
The two analog fields are always `0.0`. PSAMPLE numbers its channels the other way
round (channel 1 = coincidences).

Values are counts per second, counted over the `qrate` period: at `qrate 1` they come
in steps of 10, at `qrate 10` they are plain integers. The counting interval set on
the touch screen plays no part.

`[n]` goes up by one per printed line, continues across stopping `showc`, reconnecting
and changing `qrate`, and restarts at 0 on power-up. Since TCP loses nothing inside a
connection and the device prints nothing while disconnected, `[n]` never skips or
repeats in practice. The driver logs a warning if it does and keeps the sample; every
sample's `[n]` is stored in the acquisition file. Lost data shows up as lost time,
which the app records as connection events.

## Open questions

- [ ] What does the touch-screen counting interval affect, if not `showc`?
- [ ] What `qrate` does the device use after power-up? (The app sets it before every acquisition.)
- [ ] Which firmware versions are in the field?
- [ ] A real PSAMPLE `.crv` file and a corrected TAC export.

## Where the device facts live in the code

| Fact | Code |
| --- | --- |
| Field order, line ending, prompts, login, idle timeout, keepalive | constants at the top of `packages/twilite/src/twilite/protocol.py` |
| Banner, help, error messages, `[n]` and count model | `sim/server.py`, `Counter` in `sim/scenarios.py` |
| Report rate after power-up (not observed) | `DEFAULT_QRATE` in `sim/server.py` |
| `.crv` layout | `CRV_DATE_FORMAT`, `CRV_TIME_FORMAT`, `export_crv` in `storage.py` |
| Sample time in the PMOD export | `export_pmod_blood` in `storage.py` |
| Isotope values to verify | `isotopes.py` |
