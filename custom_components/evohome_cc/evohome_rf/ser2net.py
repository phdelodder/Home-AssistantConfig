#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
"""Evohome RF - A raw ser2net (local) serial_port to (remote) network relay."""

import asyncio
import logging
from string import printable
from typing import Optional

from .const import _dev_mode_

# timeouts in seconds, 0 means no timeout
RECV_TIMEOUT = 0  # without hearing from client (from network) - not useful
SEND_TIMEOUT = 0  # without hearing from server (from serial port)

SE_ = 240  # Subnegotiation Ends
NOP = 241  # No OPeration
DM_ = 242  # Data Mark
BRK = 243  # Break

IP_ = 244  # Interrupt Process
AO_ = 245  # Abort Output
AYT = 246  # Are You There
EC_ = 247  # Erase Character
EL_ = 248  # Erase Line

GA_ = 249  # Go Ahead
SB_ = 250  # Subnegotiation Begins
IAC = 255  # Interpret as Command

WILL = 251  # Will <option code>
WONT = 252  # Wont <option code>
DO__ = 253  # Do <option code>
DONT = 254  # Don't <option code>

DEV_MODE = _dev_mode_

_LOGGER = logging.getLogger(__name__)
if DEV_MODE:
    _LOGGER.setLevel(logging.DEBUG)


class Ser2NetProtocol(asyncio.Protocol):
    """A TCP socket interface."""

    def __init__(self, loop) -> None:
        _LOGGER.debug("Ser2NetProtocol.__init__()")

        self._loop = loop
        self.transport = None

        if RECV_TIMEOUT:
            self.timeout_handle = self._loop.call_later(
                RECV_TIMEOUT, self._recv_timeout
            )

    def _recv_timeout(self):
        _LOGGER.debug("Ser2NetProtocol._recv_timeout()")
        self.transport.close()

        _LOGGER.debug(" - socket closed by server (%ss of inactivity).", RECV_TIMEOUT)

    def connection_made(self, transport) -> None:
        _LOGGER.debug("Ser2NetProtocol.connection_made(%s)", transport)

        self.transport = transport
        _LOGGER.debug(" - connection from: %s", transport.get_extra_info("peername"))

    def data_received(self, data) -> None:
        _LOGGER.debug("Ser2NetProtocol.data_received(%s)", data)
        _LOGGER.debug(" - packet received from network: %s", data)

        operation = None
        option = None

        if self.timeout_handle:
            self.timeout_handle.cancel()
            self.timeout_handle = self._loop.call_later(
                RECV_TIMEOUT, self._recv_timeout
            )

        if int(data[0], 16) == IAC:  # telnet IAC
            # see: https://users.cs.cf.ac.uk/Dave.Marshall/Internet/node141.html
            # see: https://tools.ietf.org/html/rfc854 - telnet
            # see: https://tools.ietf.org/html/rfc2217 - ser2net
            operation, option = int(data[1], 16), int(data[2], 16)
            _LOGGER.warning(" - received a IAC (%s) %s", operation, option)
            if operation in (WILL, DO__):
                response = IAC + WONT + option  # noqa
            return  # TODO: will probably need to send a response

        elif int(data[0], 16) > 0x7F:  # other non-ASCII character
            _LOGGER.warning(" - received a %s", operation, option)
            return

        try:
            cmd = "".join(
                c
                for c in data.decode("ascii", errors="ignore").strip()
                if c in printable
            )
        except UnicodeDecodeError:
            return

        # pkt = Packet(cmd)
        # cmd = Command(pkt)
        # self._que.put_nowait(cmd)  # TODO: use factory: shld be Command, not str
        # TODO: the previous line be something like
        self._gwy.send_data(cmd)
        _LOGGER.debug(" - command sent to dispatch queue: %s", cmd)

    def eof_received(self) -> Optional[bool]:
        _LOGGER.debug("Ser2NetProtocol.eof_received()")
        _LOGGER.debug(" - socket closed by client.")

    def connection_lost(self, exc) -> None:
        _LOGGER.debug("Ser2NetProtocol.connection_lost(%s)", exc)


class Ser2NetServer:
    """A raw ser2net (local) serial_port to (remote) network relay."""

    # goal: ser2net -C 127.0.0.1,5000:raw:0:/dev/ttyUSB0:115200,8DATABITS,NONE,1STOPBIT

    def __init__(self, addr_port, cmd_que, loop=None) -> None:
        _LOGGER.debug("Ser2NetServer.__init__(%s, %s)", addr_port, cmd_que)

        self._addr, self._port = addr_port.split(":")
        self._loop = loop if loop else asyncio.get_running_loop()
        self.protocol = self.server = None

    def _send_timeout(self):
        _LOGGER.debug("Ser2NetServer._send_timeout()")
        self.protocol.transport.close()

        _LOGGER.debug(" - socket closed by server (%ss of inactivity).", SEND_TIMEOUT)

    async def start(self) -> None:
        _LOGGER.debug("Ser2NetServer.start()")

        self.protocol = Ser2NetProtocol()
        self.server = await self._loop.create_server(
            lambda: self.protocol, self._addr, int(self._port)
        )
        self._loop.create_task(self.server.serve_forever())
        _LOGGER.debug(" - listening on %s:%s", self._addr, int(self._port))

    async def write(self, data: str) -> None:
        _LOGGER.debug("Ser2NetServer.write(%s)", data)

        packet = f"{data}\r\n".encode("ascii")
        _LOGGER.debug(" - packet is: %s", packet)

        if self.protocol.transport and not self.protocol.transport.is_closing():
            self.protocol.transport.write(packet)
            _LOGGER.debug(" - data sent to network: %s", packet)
        else:
            _LOGGER.debug(" - no active network socket, unable to relay")


"""This is how to invoke the code:

    if self.config.get("ser2net_server"):
        self._relay = Ser2NetServer(
            self.config["ser2net_server"], self._que, loop=self._loop
        )
        self._tasks.append(self._loop.create_task(self._relay.start()))

"""
