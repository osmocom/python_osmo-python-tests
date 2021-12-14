#!/usr/bin/env python3
# -*- mode: python-mode; py-indent-tabs-mode: nil -*-
"""
/*
 * Copyright (C) 2016-2017 sysmocom s.f.m.c. GmbH
 *
 * All Rights Reserved
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 3 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 */
"""

from optparse import OptionParser
from osmopy.osmo_ipa import Ctrl
import socket

verbose = False

def connect(host, port):
        if verbose:
                print("Connecting to host %s:%i" % (host, port))

        sck = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sck.setblocking(1)
        sck.connect((host, port))
        return sck

def do_set_get(sck, var, value = None):
        _leftovers(sck, socket.MSG_DONTWAIT)
        (r, c) = Ctrl().cmd(var, value)
        sck.send(c)
        while True:
                ret = sck.recv(4096)
                # handle multiple messages, ignore TRAPs
                ret = Ctrl().skip_traps(ret)
                if ret != None:
                    (i, k, v) = Ctrl().parse(ret)
                    break;
        return (Ctrl().rem_header(ret),) + Ctrl().verify(ret, r, var, value)

def set_var(sck, var, val):
        (a, _, _) = do_set_get(sck, var, val)
        return a

def _leftovers(sck, fl):
        """
        Read outstanding data if any according to flags
        """
        try:
                data = sck.recv(1024, fl)
        except socket.error as _:
                return False
        if len(data) != 0:
                tail = data
                while True:
                        (head, tail) = Ctrl().split_combined(tail)
                        print("Got message:", Ctrl().rem_header(head))
                        if len(tail) == 0:
                                break
                return True
        return False

if __name__ == '__main__':
        parser = OptionParser("Usage: %prog [options] var [value]")
        parser.add_option("-d", "--host", dest="host",
                          help="connect to HOST", metavar="HOST")
        parser.add_option("-p", "--port", dest="port", type="int",
                          help="use PORT", metavar="PORT", default=4249)
        parser.add_option("-g", "--get", action="store_true",
                          dest="cmd_get", help="perform GET operation")
        parser.add_option("-s", "--set", action="store_true",
                          dest="cmd_set", help="perform SET operation")
        parser.add_option("-v", "--verbose", action="store_true",
                          dest="verbose", help="be verbose", default=False)
        parser.add_option("-m", "--monitor", action="store_true",
                          dest="monitor", help="monitor the connection for traps", default=False)

        (options, args) = parser.parse_args()

        verbose = options.verbose

        if options.cmd_set and options.cmd_get:
                parser.error("Get and set options are mutually exclusive!")

        if not (options.cmd_get or options.cmd_set or options.monitor):
                parser.error("One of -m, -g, or -s must be set")

        if not (options.host):
                parser.error("Destination host and port required!")

        sock = connect(options.host, options.port)

        if options.cmd_set:
                if len(args) < 2:
                        parser.error("Set requires var and value arguments")
                print("Got message:", set_var(sock, args[0], ' '.join(args[1:])))

        if options.cmd_get:
                if len(args) != 1:
                        parser.error("Get requires the var argument")
                (a, _, _) = do_set_get(sock, args[0])
                print("Got message:", a)

        if options.monitor:
                while True:
                        if not _leftovers(sock, 0):
                                print("Connection is gone.")
                                break
        sock.close()
