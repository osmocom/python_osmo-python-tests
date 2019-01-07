#!/usr/bin/python3
# -*- mode: python-mode; py-indent-tabs-mode: nil -*-
"""
/*
 * Copyright (C) 2018 sysmocom s.f.m.c. GmbH
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

__version__ = "0.1.1" # bump this on every non-trivial change

import argparse, os, logging, logging.handlers, datetime
import hashlib
import json
import configparser
from functools import partial
from distutils.version import StrictVersion as V
from twisted.internet import defer, reactor
from treq import post, collect
from osmopy.trap_helper import debug_init, get_type, get_r, p_h, gen_hash, make_params, comm_proc
from osmopy.twisted_ipa import CTRL, IPAFactory, __version__ as twisted_ipa_version
from osmopy.osmo_ipa import Ctrl

# we don't support older versions of TwistedIPA module
assert V(twisted_ipa_version) > V('0.4')

def log_duration(log, bid, ts, ts_http):
    """
    Log human-readable duration from timestamps
    """
    base = datetime.datetime.now()
    delta_t = datetime.timedelta(seconds = (base - ts).total_seconds())
    delta_h = datetime.timedelta(seconds = (base - ts_http).total_seconds())
    delta_w = delta_t - delta_h
    log.debug('Request for BSC %s took %s total (%s wait, %s http)' % (bid, delta_t, delta_w, delta_h))

def handle_reply(ts, ts_http, bid, f, log, resp):
    """
    Reply handler: process raw CGI server response, function f to run for each command
    """
    decoded = json.loads(resp.decode('utf-8'))
    log_duration(log, bid, ts, ts_http)
    comm_proc(decoded.get('commands'), bid, f, log)

def make_async_req(ts, dst, par, f_write, f_log, tout):
    """
    Assemble deferred request parameters and partially instantiate response handler
    """
    d = post(dst, par, timeout=tout)
    d.addCallback(collect, partial(handle_reply, ts, datetime.datetime.now(), par['bsc_id'], f_write, f_log))
    d.addErrback(lambda e: f_log.critical("HTTP POST error %s while trying to register BSC %s on %s (timeout %d)" % (repr(e), par['bsc_id'], dst, tout))) # handle HTTP errors
    return d

class Trap(CTRL):
    """
    TRAP handler (agnostic to factory's client object)
    """
    def ctrl_TRAP(self, data, op_id, v):
        """
        Parse CTRL TRAP and dispatch to appropriate handler after normalization
        """
        if get_type(v) == 'location-state':
            p = p_h(v)
            self.handle_locationstate(p(1), p(3), p(5), p(7), get_r(v))
        else:
            self.factory.log.debug('Ignoring TRAP %s' % (v.split()[0]))

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
        self.factory.log.info("Connected to CTRL@%s:%d" % (self.factory.addr_ctrl, self.factory.port_ctrl))
        super(CTRL, self).connectionMade()

    def handle_locationstate(self, net, bsc, bts, trx, data):
        """
        Handle location-state TRAP: parse trap content, build CGI Request and use treq's routines to post it while setting up async handlers
        """
        params = make_params(bsc, data)
        self.factory.log.info('location-state@%s.%s.%s.%s (%s) => %s' % (net, bsc, bts, trx, params['time_stamp'], data))
        params['h'] = gen_hash(params, self.factory.secret_key)
        t = datetime.datetime.now()
        self.factory.log.debug('Preparing request for BSC %s @ %s...' % (params['bsc_id'], t))
        # Ensure that we run only limited number of requests in parallel:
        self.factory.semaphore.run(make_async_req, t, self.factory.location, params, self.transport.write, self.factory.log, self.factory.timeout)


class TrapFactory(IPAFactory):
    """
    Store CGI information so TRAP handler can use it for requests
    """
    def __init__(self, proto, log):
        self.log = log
        level = self.log.getEffectiveLevel()
        self.log.setLevel(logging.WARNING) # we do not need excessive debug from lower levels
        super(TrapFactory, self).__init__(proto, self.log)
        self.log.setLevel(level)
        self.log.debug("Using Osmocom IPA library v%s" % Ctrl.version)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description='Proxy between given GCI service and Osmocom CTRL protocol.')
    p.add_argument('-v', '--version', action='version', version=("%(prog)s v" + __version__))
    p.add_argument('-d', '--debug', action='store_true', help="Enable debug log") # keep in sync with debug_init call below
    p.add_argument('-c', '--config-file', required=True, help="Path to mandatory config file (in INI format).")
    args = p.parse_args(namespace=TrapFactory)

    log = debug_init('CTRL2CGI', args.debug)

    T = TrapFactory(Trap, log)

    config = configparser.ConfigParser(interpolation=None)
    config.read(args.config_file)

    T.addr_ctrl = config['main'].get('addr_ctrl', 'localhost')
    T.port_ctrl = config['main'].getint('port_ctrl', 4250)
    T.timeout = config['main'].getint('timeout', 30)
    T.semaphore = defer.DeferredSemaphore(config['main'].getint('num_max_conn', 5))
    T.location = config['main'].get('location')
    T.secret_key = config['main'].get('secret_key')

    log.info("CGI proxy v%s starting with PID %d:" % (__version__, os.getpid()))
    log.info("destination %s (concurrency %d)" % (T.location, T.semaphore.limit))
    log.info("connecting to %s:%d..." % (T.addr_ctrl, T.port_ctrl))
    reactor.connectTCP(T.addr_ctrl, T.port_ctrl, T)
    reactor.run()
