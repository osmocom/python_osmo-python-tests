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

__version__ = "0.0.1" # bump this on every non-trivial change

from twisted.internet import defer, reactor
from osmopy.twisted_ipa import CTRL, IPAFactory, __version__ as twisted_ipa_version
from osmopy.osmo_ipa import Ctrl
from treq import post, collect
from functools import partial
from osmopy.trap_helper import Trap, reloader, debug_init
from distutils.version import StrictVersion as V # FIXME: use NormalizedVersion from PEP-386 when available
import argparse, datetime, signal, sys, os, logging, logging.handlers
import hashlib
import json
import configparser

# we don't support older versions of TwistedIPA module
assert V(twisted_ipa_version) > V('0.4')


@defer.inlineCallbacks
def handle_reply(f, log, resp):
    """
    Reply handler: process raw CGI server response, function f to run for each command
    """
    #log.debug('HANDLE_REPLY: code=%r' % (resp.code))
    #for key,val in resp.headers.getAllRawHeaders():
    #    log.debug('HANDLE_REPLY: key=%r val=%r' % (key, val))
    if resp.code != 200:
        resp_body = yield resp.text()
        log.critical('Received HTTP response %d: %s' % (resp.code, resp_body))
        return

    parsed = yield resp.json()
    #log.debug("RESPONSE: %r" % (parsed))
    bsc_id = parsed.get('commands')[0].split()[0].split('.')[3] # we expect 1st command to have net.0.bsc.666.bts.2.trx.1 location prefix format
    log.info("Received CGI response for BSC %s with %d commands, error status: %s" % (bsc_id, len(parsed.get('commands')), parsed.get('error')))
    log.debug("BSC %s commands: %r" % (bsc_id, parsed.get('commands')))
    for t in parsed.get('commands'): # Process commands format
        (_, m) = Ctrl().cmd(*t.split())
        f(m)

def gen_hash(params, skey):
    input = ''
    for key in ['time_stamp','position_validity','admin_status','policy_status']:
        input += str(params.get(key))
    input += skey
    for key in ['bsc_id','lat','lon','position_validity']:
        input += str(params.get(key))
    m = hashlib.md5()
    m.update(input.encode('utf-8'))
    res = m.hexdigest()
    #print('HASH: \nparams="%r"\ninput="%s" \nres="%s"' %(params, input, res))
    return res


class TrapFactory(IPAFactory):
    """
    Store CGI information so TRAP handler can use it for requests
    """
    location = None
    log = None
    semaphore = None
    client = None
    host = None
    port = None
    secret_key = None
    def __init__(self, host, port, proto, semaphore, log, location, secret_key):
        self.host = host # for logging only,
        self.port = port # seems to be no way to get it from ReconnectingClientFactory
        self.log = log
        self.semaphore = semaphore
        self.location = location
        self.secret_key = secret_key
        level = self.log.getEffectiveLevel()
        self.log.setLevel(logging.WARNING) # we do not need excessive debug from lower levels
        super(TrapFactory, self).__init__(proto, self.log)
        self.log.setLevel(level)
        self.log.debug("Using IPA %s, CGI server: %s" % (Ctrl.version, self.location))

    def prepare_params(bsc, lon, lat, fix, tstamp, oper, admin, policy):
        params = {'bsc_id': bsc, 'lon': lon, 'lat': lat, 'position_validity': fix, 'time_stamp': tstamp, 'oper_status': oper, 'admin_status': admin, 'policy_status': policy }
        params['h'] = gen_hash(params, self.factory.secret_key)
        d = post(self.factory.location, None, params=params)
        d.addCallback(partial(handle_reply, self.transport.write, self.factory.log))
        return d

if __name__ == '__main__':
    p = argparse.ArgumentParser(description='Proxy between given GCI service and Osmocom CTRL protocol.')
    p.add_argument('-v', '--version', action='version', version=("%(prog)s v" + __version__))
    p.add_argument('-a', '--addr-ctrl', default='localhost', help="Adress to use for CTRL interface, defaults to localhost")
    p.add_argument('-p', '--port-ctrl', type=int, default=4250, help="Port to use for CTRL interface, defaults to 4250")
    p.add_argument('-n', '--num-max-conn', type=int, default=5, help="Max number of concurrent HTTP requests to CGI server")
    p.add_argument('-d', '--debug', action='store_true', help="Enable debug log") # keep in sync with debug_init call below
    p.add_argument('-o', '--output', action='store_true', help="Log to STDOUT in addition to SYSLOG")
    p.add_argument('-l', '--location', help="Location URL of the CGI server")
    p.add_argument('-s', '--secret-key', help="Secret key used to generate verification token")
    p.add_argument('-c', '--config-file', help="Path Config file. Cmd line args override values in config file")
    args = p.parse_args()

    log = debug_init('CTRL2CGI', args.debug, args.output)

    location_cfgfile = None
    secret_key_cfgfile = None
    port_ctrl_cfgfile = None
    addr_ctrl_cfgfile = None
    num_max_conn_cfgfile = None
    if args.config_file:
        config = configparser.ConfigParser()
        config.read(args.config_file)
        if 'main' in config:
            location_cfgfile = config['main'].get('location', None)
            secret_key_cfgfile = config['main'].get('secret_key', None)
            addr_ctrl_cfgfile = config['main'].get('addr_ctrl', None)
            port_ctrl_cfgfile = config['main'].get('port_ctrl', None)
            num_max_conn_cfgfile = config['main'].get('num_max_conn', None)
    location = args.location if args.location is not None else location_cfgfile
    secret_key = args.secret_key  if args.secret_key is not None else secret_key_cfgfile
    addr_ctrl = args.addr_ctrl if args.addr_ctrl is not None else addr_ctrl_cfgfile
    port_ctrl = args.port_ctrl if args.port_ctrl is not None else port_ctrl_cfgfile
    num_max_conn = args.num_max_conn if args.num_max_conn is not None else num_max_conn_cfgfile

    log.info("CGI proxy %s starting with PID %d ..." % (__version__, os.getpid()))
    reactor.connectTCP(addr_ctrl, port_ctrl, TrapFactory(addr_ctrl, port_ctrl, Trap, defer.DeferredSemaphore(num_max_conn), log, location, secret_key))
    reactor.run()
