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

__version__ = "0.7.2" # bump this on every non-trivial change

import argparse, os, logging
from functools import partial
from distutils.version import StrictVersion as V # FIXME: use NormalizedVersion from PEP-386 when available
from twisted.internet import defer, reactor
from suds.client import Client
from treq import post, collect
from osmopy.trap_helper import debug_init, get_type, get_r, p_h, make_params, comm_proc
from osmopy.twisted_ipa import CTRL, IPAFactory, __version__ as twisted_ipa_version
from osmopy.osmo_ipa import Ctrl

# we don't support older versions of TwistedIPA module
assert V(twisted_ipa_version) > V('0.4')


def handle_reply(p, f, log, r):
    """
    Reply handler: takes function p to process raw SOAP server reply r, function f to run for each command
    """
    repl = p(r) # result is expected to have both commands[] array and error string (could be None)
    bsc_id = comm_proc(repl.commands, f, log)
    log.info("Received SOAP response for BSC %s with %d commands, error status: %s" % (bsc_id, len(repl.commands), repl.error))


class Trap(CTRL):
    """
    TRAP handler (agnostic to factory's client object)
    """
    def ctrl_TRAP(self, data, op_id, v):
        """
        Parse CTRL TRAP and dispatch to appropriate handler after normalization
        """
        self.factory.log.debug('TRAP %s' % v)
        t_type = get_type(v)
        p = p_h(v)
        method = getattr(self, 'handle_' + t_type.replace('-', ''), lambda *_: "Unhandled %s trap" % t_type)
        method(p(1), p(3), p(5), p(7), get_r(v))

    def ctrl_SET_REPLY(self, data, _, v):
        """
        Debug log for replies to our commands
        """
        self.factory.log.debug('SET REPLY %s' % v)

    def ctrl_ERROR(self, data, op_id, v):
        """
        We want to know if smth went wrong
        """
        self.factory.log.debug('CTRL ERROR [%s] %s' % (op_id, v))

    def connectionMade(self):
        """
        Logging wrapper, calling super() is necessary not to break reconnection logic
        """
        self.factory.log.info("Connected to CTRL@%s:%d" % (self.factory.host, self.factory.port))
        super(CTRL, self).connectionMade()

    @defer.inlineCallbacks
    def handle_locationstate(self, net, bsc, bts, trx, data):
        """
        Handle location-state TRAP: parse trap content, build SOAP context and use treq's routines to post it while setting up async handlers
        """
        params = make_params(bsc, data)
        self.factory.log.debug('location-state@%s.%s.%s.%s (%s) => %s' % (net, bsc, bts, trx, params['time_stamp'], data))
        ctx = self.factory.client.registerSiteLocation(bsc, float(params['lon']), float(params['lat']), params['position_validity'], params['time_stamp'], params['oper_status'], params['admin_status'], params['policy_status'])
        d = post(self.factory.location, ctx.envelope)
        d.addCallback(collect, partial(handle_reply, ctx.process_reply, self.transport.write, self.factory.log)) # treq's collect helper is handy to get all reply content at once using closure on ctx
        d.addErrback(lambda e, bsc: self.factory.log.critical("HTTP POST error %s while trying to register BSC %s on %s" % (e, bsc, self.factory.location)), bsc) # handle HTTP errors
        # Ensure that we run only limited number of requests in parallel:
        yield self.factory.semaphore.acquire()
        yield d # we end up here only if semaphore is available which means it's ok to fire the request without exceeding the limit
        self.factory.semaphore.release()

    def handle_notificationrejectionv1(self, net, bsc, bts, trx, data):
        """
        Handle notification-rejection-v1 TRAP: just an example to show how more message types can be handled
        """
        self.factory.log.debug('notification-rejection-v1@bsc-id %s => %s' % (bsc, data))


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


if __name__ == '__main__':
    p = argparse.ArgumentParser(description='Proxy between given SOAP service and Osmocom CTRL protocol.')
    p.add_argument('-v', '--version', action='version', version=("%(prog)s v" + __version__))
    p.add_argument('-p', '--port', type=int, default=4250, help="Port to use for CTRL interface, defaults to 4250")
    p.add_argument('-c', '--ctrl', default='localhost', help="Adress to use for CTRL interface, defaults to localhost")
    p.add_argument('-w', '--wsdl', required=True, help="WSDL URL for SOAP")
    p.add_argument('-n', '--num', type=int, default=5, help="Max number of concurrent HTTP requests to SOAP server")
    p.add_argument('-d', '--debug', action='store_true', help="Enable debug log") # keep in sync with debug_init call below
    p.add_argument('-l', '--location', help="Override location found in WSDL file (don't use unless you know what you're doing)")
    args = p.parse_args()

    log = debug_init('CTRL2SOAP', args.debug)

    log.info("SOAP proxy %s starting with PID %d ..." % (__version__, os.getpid()))
    reactor.connectTCP(args.ctrl, args.port, TrapFactory(args.ctrl, args.port, Trap, defer.DeferredSemaphore(args.num), log, args.wsdl, args.location))
    reactor.run()
