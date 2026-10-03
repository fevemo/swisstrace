"""Command line of the simulator: ``python -m twilite.sim --scenario ...``."""

from __future__ import annotations

import argparse
import asyncio
import logging

from twilite import protocol
from twilite.isotopes import ISOTOPES
from twilite.sim.scenarios import SCENARIOS
from twilite.sim.server import DEFAULT_PORT, Faults, TwiliteSimulator


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m twilite.sim", description="Simulated Swisstrace twilite.")
    parser.add_argument("--host", default="127.0.0.1", help="interface to listen on (default: %(default)s)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="TCP port (default: %(default)s)")
    parser.add_argument("--scenario", choices=sorted(SCENARIOS), default="background")
    parser.add_argument("--isotope", choices=sorted(ISOTOPES), default="F-18")
    parser.add_argument("--transcript", help="recorded session for --scenario replay")
    parser.add_argument("--seed", type=int, default=1, help="random seed (default: %(default)s)")
    parser.add_argument("--idle-timeout", type=float, default=protocol.IDLE_TIMEOUT_S, metavar="S",
                        help="close a connection idle at the prompt for S seconds, 0 for never "
                             "(default: %(default)s, as the device)")
    faults = parser.add_argument_group("fault injection")
    faults.add_argument("--drop-after", type=int, metavar="N", help="close the connection after N report lines")
    faults.add_argument("--stall-after", type=int, metavar="N", help="go silent after N report lines ...")
    faults.add_argument("--stall-seconds", type=float, default=10.0, metavar="S", help="... for S seconds")
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(message)s")
    faults = Faults(drop_after=args.drop_after, stall_after=args.stall_after, stall_s=args.stall_seconds)
    simulator = TwiliteSimulator(
        scenario=args.scenario, isotope=args.isotope, host=args.host, port=args.port, seed=args.seed,
        faults=faults, transcript=args.transcript, idle_timeout_s=args.idle_timeout,
    )

    async def serve() -> None:
        await simulator.start()
        print(f"Simulated twilite ({args.scenario}) listening on {args.host}:{simulator.port}. Ctrl+C to stop.")
        await asyncio.Event().wait()

    try:
        asyncio.run(serve())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
