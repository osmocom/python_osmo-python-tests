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

__version__ = "0.0.6" # bump this on every non-trivial change

import argparse, os, logging, logging.handlers
import hashlib
import json
import configparser
from functools import partial
from distutils.version import StrictVersion as V # FIXME: use NormalizedVersion from PEP-386 when available
from twisted.internet import defer, reactor
from treq import post, collect
from osmopy.trap_helper import debug_init, get_type, get_r, p_h, make_params, comm_proc
from osmopy.twisted_ipa import CTRL, IPAFactory, __version__ as twisted_ipa_version
from osmopy.osmo_ipa import Ctrl

# we don't support older versions of TwistedIPA module
assert V(twisted_ipa_version) > V('0.4')


def handle_reply(bid, f, log, resp):
    """
    Reply handler: process raw CGI server response, function f to run for each command
    """
    decoded = json.loads(resp.decode('utf-8'))
    comm_proc(decoded.get('commands'), bid, f, log)

def gen_hash(params, skey):
    inp = ''
    for key in ['time_stamp', 'position_validity', 'admin_status', 'policy_status']:
        inp += str(params.get(key))
    inp += skey
    for key in ['bsc_id', 'lat', 'lon', 'position_validity']:
        inp += str(params.get(key))
    m = hashlib.md5()
    m.update(inp.encode('utf-8'))
    res = m.hexdigest()
    #print('HASH: \nparams="%r"\ninput="%s" \nres="%s"' %(params, input, res))
    return res

def make_async_req(dst, par, f_write, f_log):
    d = post(dst, par)
    d.addCallback(collect, partial(handle_reply, par['bsc_id'], f_write, f_log)) # treq's collect helper is handy to get all reply content at once
    d.addErrback(lambda e: f_log.critical("HTTP POST error %s while trying to register BSC %s on %s" % (e, par['bsc_id'], dst))) # handle HTTP errors
    return d

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
        self.factory.log.info("Connected to CTRL@%s:%d" % (self.factory.addr_ctrl, self.factory.port_ctrl))
        super(CTRL, self).connectionMade()

    def handle_locationstate(self, net, bsc, bts, trx, data):
        """
        Handle location-state TRAP: parse trap content, build CGI Request and use treq's routines to post it while setting up async handlers
        """
        params = make_params(bsc, data)
        self.factory.log.info('location-state@%s.%s.%s.%s (%s) => %s' % (net, bsc, bts, trx, params['time_stamp'], data))
        params['h'] = gen_hash(params, self.factory.secret_key)
        # Ensure that we run only limited number of requests in parallel:
        self.factory.semaphore.run(make_async_req, self.factory.location, params, self.transport.write, self.factory.log)

    def handle_notificationrejectionv1(self, net, bsc, bts, trx, data):
        """
        Handle notification-rejection-v1 TRAP: just an example to show how more message types can be handled
        """
        self.factory.log.debug('notification-rejection-v1@bsc-id %s => %s' % (bsc, data))


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
    T.semaphore = defer.DeferredSemaphore(config['main'].getint('num_max_conn', 5))
    T.location = config['main'].get('location')
    T.secret_key = config['main'].get('secret_key')

    log.info("CGI proxy v%s starting with PID %d:" % (__version__, os.getpid()))
    log.info("destination %s (concurrency %d)" % (T.location, T.semaphore.limit))
    log.info("connecting to %s:%d..." % (T.addr_ctrl, T.port_ctrl))
    reactor.connectTCP(T.addr_ctrl, T.port_ctrl, T)
    reactor.run()
