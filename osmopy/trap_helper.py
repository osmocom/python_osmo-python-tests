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

import sys, os, signal, logging, logging.handlers
from functools import partial
from osmopy.twisted_ipa import CTRL
from twisted.internet import defer

# keys from OpenBSC openbsc/src/libbsc/bsc_rf_ctrl.c, values SOAP-specific
oper = { 'inoperational' : 0, 'operational' : 1 }
admin = { 'locked' : 0, 'unlocked' : 1 }
policy = { 'off' : 0, 'on' : 1, 'grace' : 2, 'unknown' : 3 }

# keys from OpenBSC openbsc/src/libbsc/bsc_vty.c
fix = { 'invalid' : 0, 'fix2d' : 1, 'fix3d' : 1 } # SOAP server treats it as boolean but expects int

class Trap(CTRL):
    """
    TRAP handler (agnostic to factory's client object)
    """
    def ctrl_TRAP(self, data, op_id, v):
        """
        Parse CTRL TRAP and dispatch to appropriate handler after normalization
        """
        self.factory.log.debug('TRAP %s' % v)
        (l, r) = v.split()
        loc = l.split('.')
        t_type = loc[-1]
        p = partial(lambda a, i: a[i] if len(a) > i else None, loc) # parse helper
        method = getattr(self, 'handle_' + t_type.replace('-', ''), lambda *_: "Unhandled %s trap" % t_type)
        method(p(1), p(3), p(5), p(7), r) # we expect net.0.bsc.666.bts.2.trx.1 format for trap prefix

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
        Handle location-state TRAP: parse trap content, prepare parameters and use treq's routines to post it while setting up async handlers
        """
        (ts, fx, lat, lon, height, opr, adm, pol, mcc, mnc) = data.split(',')
        tstamp = datetime.datetime.fromtimestamp(float(ts)).isoformat()
        self.factory.log.debug('location-state@%s.%s.%s.%s (%s) [%s/%s] => %s' % (net, bsc, bts, trx, tstamp, mcc, mnc, data))

        d = self.factory.prepare_params(bsc, lon, lat, fix.get(fx, 0), tstamp, oper.get(opr, 2), admin.get(adm, 2), policy.get(pol, 3))

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


def reloader(path, script, log, dbg1, dbg2, signum, _):
    """
    Signal handler: we have to use execl() because twisted's reactor is not restartable due to some bug in twisted implementation
    """
    log.info("Received Signal %d - restarting..." % signum)
    if signum == signal.SIGUSR1 and dbg1 not in sys.argv and dbg2 not in sys.argv:
        sys.argv.append(dbg1) # enforce debug
    if signum == signal.SIGUSR2 and (dbg1 in sys.argv or dbg2 in sys.argv): # disable debug
        if dbg1 in sys.argv:
            sys.argv.remove(dbg1)
        if dbg2 in sys.argv:
            sys.argv.remove(dbg2)
    os.execl(path, script, *sys.argv[1:])

def debug_init(name, is_debug, output):
    log = logging.getLogger(name)
    if is_debug:
        log.setLevel(logging.DEBUG)
    else:
        log.setLevel(logging.INFO)
    log.addHandler(logging.handlers.SysLogHandler('/dev/log'))
    if output:
        log.addHandler(logging.StreamHandler(sys.stdout))

    reboot = partial(reloader, os.path.abspath(__file__), os.path.basename(__file__), log, '-d', '--debug') # keep in sync with caller's add_argument()
    signal.signal(signal.SIGHUP, reboot)
    signal.signal(signal.SIGQUIT, reboot)
    signal.signal(signal.SIGUSR1, reboot) # restart and enabled debug output
    signal.signal(signal.SIGUSR2, reboot) # restart and disable debug output

    return log
