#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
"""A CLI for the evohome_rf library.

    evohome_rf is used to parse/process Honeywell's RAMSES-II packets.
    """

import asyncio
import json
import sys
from typing import Tuple

import click
from colorama import init as colorama_init, Fore, Style

from evohome_rf import Gateway, GracefulExit
from evohome_rf.discovery import (
    EXECUTE_CMD,
    GET_FAULTS,
    GET_SCHED,
    SET_SCHED,
    SCAN_DISC,
    SCAN_FULL,
    SCAN_HARD,
    SCAN_XXXX,
    spawn_execute_scripts,
    spawn_monitor_scripts,
)
from evohome_rf.exceptions import EvohomeError
from evohome_rf.helpers import is_valid_dev_id
from evohome_rf.packet import CONSOLE_COLS
from evohome_rf.schema import (
    ALLOW_LIST,
    CONFIG,
    DISABLE_DISCOVERY,
    DISABLE_SENDING,
    DONT_CREATE_MESSAGES,
    ENFORCE_ALLOWLIST,
    EVOFW_FLAG,
    INPUT_FILE,
    PACKET_LOG,
    REDUCE_PROCESSING,
    SERIAL_PORT,
)

DEBUG_MODE = "debug_mode"

COMMAND = "command"
EXECUTE = "execute"
LISTEN = "listen"
MONITOR = "monitor"
PARSE = "parse"

DEBUG_ADDR = "0.0.0.0"
DEBUG_PORT = 5678

COLORS = {" I": Fore.GREEN, "RP": Fore.CYAN, "RQ": Fore.CYAN, " W": Fore.MAGENTA}

CONTEXT_SETTINGS = dict(help_option_names=["-h", "--help"])

LIB_KEYS = (
    INPUT_FILE,
    SERIAL_PORT,
    EVOFW_FLAG,
    PACKET_LOG,
    # "process_level",  # TODO
    REDUCE_PROCESSING,
)


def _proc_kwargs(obj, kwargs) -> Tuple[dict, dict]:
    lib_kwargs, cli_kwargs = obj
    lib_kwargs[CONFIG].update({k: v for k, v in kwargs.items() if k in LIB_KEYS})
    cli_kwargs.update({k: v for k, v in kwargs.items() if k not in LIB_KEYS})
    return lib_kwargs, cli_kwargs


def _convert_to_list(d: str) -> list:
    if not d or not str(d):
        return []
    return [c.strip() for c in d.split(",") if c.strip()]


def _arg_split(ctx, param, value):  # callback=_arg_split
    # split columns by ',' and remove whitespace
    _items = [x.strip() for x in value.split(",")]

    # validate each item
    # for x in _items:
    #     if not_valid(x):
    #         raise click.BadOptionUsage(f"{x} is not valid.")

    return _items


class DeviceIdParamType(click.ParamType):
    name = "device_id"

    def convert(self, value: str, param, ctx):
        if is_valid_dev_id(value):
            return value.upper()
        self.fail(f"{value!r} is not a valid device_id", param, ctx)


@click.group(context_settings=CONTEXT_SETTINGS)
@click.option("-z", "--debug-mode", count=True, help="enable debugger")
@click.option("-r", "--reduce-processing", count=True, help="-rrr will give packets")
@click.option("-l/-nl", "--long-dates/--no-long-dates", default=None)
@click.option("-c", "--config-file", type=click.File("r"))
@click.pass_context
def cli(ctx, config_file=None, **kwargs):
    """A CLI for the evohome_rf library."""

    if 0 < kwargs[DEBUG_MODE] < 3:
        import debugpy

        debugpy.listen(address=(DEBUG_ADDR, DEBUG_PORT))
        print(f"Debugging is enabled, listening on: {DEBUG_ADDR}:{DEBUG_PORT}.")
        print(" - execution paused, waiting for debugger to attach...")

        if kwargs[DEBUG_MODE] == 1:
            debugpy.wait_for_client()
            print(" - debugger is now attached, continuing execution.")

    lib_kwargs, cli_kwargs = _proc_kwargs(({CONFIG: {}}, {}), kwargs)

    if config_file is not None:
        lib_kwargs.update(json.load(config_file))

    lib_kwargs[DEBUG_MODE] = cli_kwargs[DEBUG_MODE] > 1
    lib_kwargs[CONFIG][REDUCE_PROCESSING] = kwargs[REDUCE_PROCESSING]

    ctx.obj = lib_kwargs, kwargs


class FileCommand(click.Command):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.params.insert(
            0, click.Argument(("input-file",), type=click.File("r"), default=sys.stdin)
        )
        # self.params.insert(1, click.Option(("-r", "--process_level"), count=True))


class PortCommand(click.Command):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.params.insert(0, click.Argument(("serial-port",)))
        # self.params.insert(1, click.Option(("-r", "--process_level"), count=True))
        self.params.insert(
            1,
            click.Option(
                ("-o", "--packet-log"),
                type=click.Path(),
                help="Log all packets to this file",
            ),
        )
        self.params.insert(
            2,
            click.Option(
                ("-T", "--evofw-flag"),
                type=click.STRING,
                help="Pass this traceflag to evofw",
            ),
        )


@click.command(cls=FileCommand)
@click.pass_obj
def parse(obj, **kwargs):
    """Parse a log file for messages/packets."""
    lib_kwargs, cli_kwargs = _proc_kwargs(obj, kwargs)

    lib_kwargs[INPUT_FILE] = lib_kwargs[CONFIG].pop(INPUT_FILE)

    asyncio.run(main(lib_kwargs, command=PARSE, **cli_kwargs))


@click.command(cls=PortCommand)
@click.option("-d/-nd", "--discover/--no-discover", default=None)
@click.option(  # "--execute-cmd"
    "-x", "--execute-cmd", type=click.STRING, help="e.g. 'RQ 01:123456 1F09 00'"
)
@click.option(
    "--poll-devices", type=click.STRING, help="e.g. 'device_id, device_id, ...'"
)
@click.pass_obj
def monitor(obj, **kwargs):
    """Monitor (eavesdrop and/or probe) a serial port for messages/packets."""
    lib_kwargs, cli_kwargs = _proc_kwargs(obj, kwargs)

    if cli_kwargs["discover"] is not None:
        lib_kwargs[CONFIG][DISABLE_DISCOVERY] = not cli_kwargs["discover"]
    lib_kwargs[CONFIG]["poll_devices"] = _convert_to_list(
        cli_kwargs.pop("poll_devices")
    )

    asyncio.run(main(lib_kwargs, command=MONITOR, **cli_kwargs))


@click.command(cls=PortCommand)
@click.option(  # "--execute-cmd"
    "-x", "--execute-cmd", type=click.STRING, help="e.g. 'RQ 01:123456 1F09 00'"
)
@click.option("-s0", "-sd", "--scan-disc", help="e.g. 'device_id, device_id, ...'")
@click.option("-s1", "-sf", "--scan-full", help="e.g. 'device_id, device_id, ...'")
@click.option("-s2", "-sh", "--scan-hard", help="e.g. 'device_id, device_id, ...'")
@click.option("-s9", "-sx", "--scan-xxxx", help="e.g. 'device_id, device_id, ...'")
@click.option("--get-faults", type=DeviceIdParamType(), help="controller_id")
@click.option(  # "--get-schedule"
    "--get-schedule",
    default=[None, None],
    type=(DeviceIdParamType(), str),
    help="controller_id, zone_idx (e.g. '0A')",
)
@click.option(  # "--set-schedule"
    "--set-schedule",
    default=[None, None],
    type=(DeviceIdParamType(), click.File("r")),
    help="controller_id, filename.json",
)
@click.pass_obj
def execute(obj, **kwargs):
    """Execute any specified scripts, return the results, then quit."""
    lib_kwargs, cli_kwargs = _proc_kwargs(obj, kwargs)

    lib_kwargs[CONFIG][DISABLE_DISCOVERY] = True

    allowed = lib_kwargs[ALLOW_LIST] = lib_kwargs.get(ALLOW_LIST, {})
    for k in (SCAN_DISC, SCAN_FULL, SCAN_HARD, SCAN_XXXX):
        cli_kwargs[k] = _convert_to_list(cli_kwargs.pop(k))
        allowed.update({d: None for d in cli_kwargs[k] if d not in allowed})

    if cli_kwargs.get(GET_FAULTS) and cli_kwargs[GET_FAULTS] not in allowed:
        allowed[cli_kwargs[GET_FAULTS]] = None

    if cli_kwargs[GET_SCHED][0] and cli_kwargs[GET_SCHED][0] not in allowed:
        allowed[cli_kwargs[GET_SCHED][0]] = None

    if cli_kwargs[SET_SCHED][0] and cli_kwargs[SET_SCHED][0] not in allowed:
        allowed[cli_kwargs[SET_SCHED][0]] = None

    if lib_kwargs[ALLOW_LIST]:
        lib_kwargs[CONFIG][ENFORCE_ALLOWLIST] = True

    asyncio.run(main(lib_kwargs, command=EXECUTE, **cli_kwargs))


@click.command(cls=PortCommand)
@click.pass_obj
def listen(obj, **kwargs):
    """Listen to (eavesdrop only) a serial port for messages/packets."""
    lib_kwargs, cli_kwargs = _proc_kwargs(obj, kwargs)

    lib_kwargs[CONFIG][DISABLE_SENDING] = True

    asyncio.run(main(lib_kwargs, command=LISTEN, **cli_kwargs))


async def main(lib_kwargs, **kwargs):
    def print_results(**kwargs):

        if kwargs[GET_FAULTS]:
            fault_log = gwy.system_by_id[kwargs[GET_FAULTS]]._fault_log.fault_log

            if fault_log is None:
                print("No fault log, or failed to get the fault log.")
            else:
                [print(f"{k:02X}", v) for k, v in fault_log.items()]

        if kwargs[GET_SCHED][0]:
            system_id, zone_idx = kwargs[GET_SCHED]
            zone = gwy.system_by_id[system_id].zone_by_idx[zone_idx]
            schedule = zone._schedule.schedule

            if schedule is None:
                print("Failed to get the schedule.")
            else:
                print("Schedule = \r\n", json.dumps(schedule))  # , indent=4))

        if kwargs[SET_SCHED][0]:
            system_id, _ = kwargs[GET_SCHED]

        # else:
        #     print(gwy.device_by_id[kwargs["device_id"]])

    def print_summary(gwy):
        if gwy.evo is None:
            print(f"Schema[gateway] = {json.dumps(gwy.schema)}\r\n")
            print(f"Params[gateway] = {json.dumps(gwy.params)}\r\n")
            print(f"Status[gateway] = {json.dumps(gwy.status)}")

        else:
            print(
                f"Schema[{repr(gwy.evo)}] = {json.dumps(gwy.evo.schema, indent=4)}\r\n"
            )
            print(
                f"Params[{repr(gwy.evo)}] = {json.dumps(gwy.evo.params, indent=4)}\r\n"
            )
            print(f"Status[{repr(gwy.evo)}] = {json.dumps(gwy.evo.status, indent=4)}")

    def process_message(msg) -> None:
        if kwargs[DEBUG_MODE]:
            dtm = f"{msg.dtm}"  # keep original timestamp
            print(f"{dtm} {msg}"[:CONSOLE_COLS])
            return

        dtm = msg.dtm if kwargs["long_dates"] else f"{msg.dtm:%H:%M:%S.%f}"[:-3]
        if msg.src.type == "18":
            print(f"{Style.BRIGHT}{COLORS.get(msg.verb)}{dtm} {msg}"[:CONSOLE_COLS])
        else:
            print(f"{COLORS.get(msg.verb)}{dtm} {msg}"[:CONSOLE_COLS])

    print("\r\nclient.py: Starting evohome_rf...")

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    gwy = Gateway(lib_kwargs[CONFIG].pop(SERIAL_PORT, None), **lib_kwargs)

    if kwargs[REDUCE_PROCESSING] < DONT_CREATE_MESSAGES:
        # no MSGs will be sent to STDOUT, so send PKTs instead
        colorama_init(autoreset=True)  # TODO: remove strip=True
        protocol, _ = gwy.create_client(process_message)

    try:  # main code here
        task = asyncio.create_task(gwy.start())

        if kwargs[COMMAND] == MONITOR:
            tasks = spawn_monitor_scripts(gwy, **kwargs)

        if kwargs[COMMAND] == EXECUTE:
            tasks = spawn_execute_scripts(gwy, **kwargs)
            await asyncio.gather(*tasks)

            cmds = (EXECUTE_CMD, SCAN_DISC, SCAN_FULL, SCAN_HARD, SCAN_XXXX)
            if not any(kwargs[k] for k in cmds):
                # await gwy.stop()
                task.cancel()

        await task

    except asyncio.CancelledError:
        msg = " - ended via: CancelledError (e.g. SIGINT)"
    except GracefulExit:
        msg = " - ended via: GracefulExit"
    except KeyboardInterrupt:
        msg = " - ended via: KeyboardInterrupt"
    except EvohomeError as err:
        msg = f" - ended via: EvohomeError: {err}"
    else:  # if no Exceptions raised, e.g. EOF when parsing
        msg = " - ended without error (e.g. EOF)"

    print("\r\nclient.py: Finished evohome_rf, results:\r\n")
    if kwargs[COMMAND] == EXECUTE:
        print_results(**kwargs)
    else:
        print_summary(gwy)

    print(f"\r\nclient.py: Finished evohome_rf.\r\n{msg}\r\n")


cli.add_command(parse)
cli.add_command(monitor)
cli.add_command(execute)
cli.add_command(listen)

if __name__ == "__main__":
    cli()
