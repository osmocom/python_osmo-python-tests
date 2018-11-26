#!/usr/bin/python3
# -*- mode: python-mode; py-indent-tabs-mode: nil -*-
"""
/*
 * Copyright (C) 2016 sysmocom s.f.m.c. GmbH
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
 *
 * You should have received a copy of the GNU General Public License along
 * with this program; if not, write to the Free Software Foundation, Inc.,
 * 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
 */
"""

__version__ = "0.7.1" # bump this on every non-trivial change

from twisted.internet import defer, reactor
from osmopy.twisted_ipa import CTRL, IPAFactory, __version__ as twisted_ipa_version
from osmopy.osmo_ipa import Ctrl
from treq import post, collect
from suds.client import Client
from functools import partial
from osmopy.trap_helper import Trap, reloader, debug_init
from distutils.version import StrictVersion as V # FIXME: use NormalizedVersion from PEP-386 when available
import argparse, datetime, signal, sys, os, logging, logging.handlers

# we don't support older versions of TwistedIPA module
assert V(twisted_ipa_version) > V('0.4')


def handle_reply(p, f, log, r):
    """
    Reply handler: takes function p to process raw SOAP server reply r, function f to run for each command and verbosity flag v
    """
    repl = p(r) # result is expected to have both commands[] array and error string (could be None)
    bsc_id = repl.commands[0].split()[0].split('.')[3] # we expect 1st command to have net.0.bsc.666.bts.2.trx.1 location prefix format
    log.info("Received SOAP response for BSC %s with %d commands, error status: %s" % (bsc_id, len(repl.commands), repl.error))
    log.debug("BSC %s commands: %s" % (bsc_id, repl.commands))
    for t in repl.commands: # Process OpenBscCommands format from .wsdl
        (_, m) = Ctrl().cmd(*t.split())
        f(m)


class TrapFactory(IPAFactory):
    """
    Store SOAP client object so TRAP handler can use it for requests
    """
    location = None
    log = None
    semaphore = None
    client = None
    host = None
    port = None
    def __init__(self, host, port, proto, semaphore, log, wsdl=None, location=None):
        self.host = host # for logging only,
        self.port = port # seems to be no way to get it from ReconnectingClientFactory
        self.log = log
        self.semaphore = semaphore
        soap = Client(wsdl, location=location, nosend=True) # make async SOAP client
        self.location = location.encode() if location else soap.wsdl.services[0].ports[0].location # necessary for dispatching HTTP POST via treq
        self.client = soap.service
        level = self.log.getEffectiveLevel()
        self.log.setLevel(logging.WARNING) # we do not need excessive debug from lower levels
        super(TrapFactory, self).__init__(proto, self.log)
        self.log.setLevel(level)
        self.log.debug("Using IPA %s, SUDS client: %s" % (Ctrl.version, soap))

    def prepare_params(bsc, lon, lat, fix, tstamp, oper, admin, policy):
        ctx = self.factory.client.registerSiteLocation(bsc, float(lon), float(lat), fix, tstamp, oper, admin, policy)
        d = post(self.factory.location, ctx.envelope)
         # treq's collect helper is handy to get all reply content at once using closure on ctx:
        d.addCallback(collect, partial(handle_reply, ctx.process_reply, self.transport.write, self.factory.log))
        return d

if __name__ == '__main__':
    p = argparse.ArgumentParser(description='Proxy between given SOAP service and Osmocom CTRL protocol.')
    p.add_argument('-v', '--version', action='version', version=("%(prog)s v" + __version__))
    p.add_argument('-p', '--port', type=int, default=4250, help="Port to use for CTRL interface, defaults to 4250")
    p.add_argument('-c', '--ctrl', default='localhost', help="Adress to use for CTRL interface, defaults to localhost")
    p.add_argument('-w', '--wsdl', required=True, help="WSDL URL for SOAP")
    p.add_argument('-n', '--num', type=int, default=5, help="Max number of concurrent HTTP requests to SOAP server")
    p.add_argument('-d', '--debug', action='store_true', help="Enable debug log") # keep in sync with debug_init call below
    p.add_argument('-o', '--output', action='store_true', help="Log to STDOUT in addition to SYSLOG")
    p.add_argument('-l', '--location', help="Override location found in WSDL file (don't use unless you know what you're doing)")
    args = p.parse_args()

    log = debug_init('CTRL2SOAP', args.debug, args.output)

    log.info("SOAP proxy %s starting with PID %d ..." % (__version__, os.getpid()))
    reactor.connectTCP(args.ctrl, args.port, TrapFactory(args.ctrl, args.port, Trap, defer.DeferredSemaphore(args.num), log, args.wsdl, args.location))
    reactor.run()
