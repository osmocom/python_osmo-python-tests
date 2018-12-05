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

import sys, os, datetime, signal, logging, logging.handlers
from functools import partial
from osmopy.osmo_ipa import Ctrl

# keys from OpenBSC openbsc/src/libbsc/bsc_rf_ctrl.c, values SOAP-specific
oper = { 'inoperational' : 0, 'operational' : 1 }
admin = { 'locked' : 0, 'unlocked' : 1 }
policy = { 'off' : 0, 'on' : 1, 'grace' : 2, 'unknown' : 3 }

# keys from OpenBSC openbsc/src/libbsc/bsc_vty.c
fix = { 'invalid' : 0, 'fix2d' : 1, 'fix3d' : 1 } # SOAP server treats it as boolean but expects int

def split_type(v):
    """
    Split TRAP type into list
    """
    (l, _) = v.split()
    return l.split('.')

def get_r(v):
    """
    Split TRAP record
    """
    (_, r) = v.split()
    return r

def get_type(v):
    """
    Get TRAP type
    """
    loc = split_type(v)
    return loc[-1]

def comm_proc(comm, f, log):
    """
    Command processor: takes function f to run for each command
    """
    bsc_id = comm[0].split()[0].split('.')[3] # we expect 1st command to have net.0.bsc.666.bts.2.trx.1 location prefix format
    log.debug("BSC %s commands: %r" % (bsc_id, comm))
    for t in comm:
        (_, m) = Ctrl().cmd(*t.split())
        f(m)
    return bsc_id

def make_params(bsc, data):
    """
    Make parameters for request
    """
    (ts, fx, lat, lon, _, opr, adm, pol, _, _) = data.split(',')
    tstamp = datetime.datetime.fromtimestamp(float(ts)).isoformat()
    return {'bsc_id': bsc, 'lon': lon, 'lat': lat, 'position_validity': fix.get(fx, 0), 'time_stamp': tstamp, 'oper_status': oper.get(opr, 2), 'admin_status': admin.get(adm, 2), 'policy_status': policy.get(pol, 3) }

def p_h(v):
    """
    Parse helper for method dispatch: expected format is net.0.bsc.666.bts.2.trx.1
    """
    loc = split_type(v)
    return partial(lambda a, i: a[i] if len(a) > i else None, loc)

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

def debug_init(name, is_debug):
    """
    Initialize signal handlers and logging
    """
    log = logging.getLogger(name)
    if is_debug:
        log.setLevel(logging.DEBUG)
    else:
        log.setLevel(logging.INFO)
    log.addHandler(logging.StreamHandler(sys.stdout))

    reboot = partial(reloader, os.path.abspath(__file__), os.path.basename(__file__), log, '-d', '--debug') # keep in sync with caller's add_argument()
    signal.signal(signal.SIGHUP, reboot)
    signal.signal(signal.SIGQUIT, reboot)
    signal.signal(signal.SIGUSR1, reboot) # restart and enabled debug output
    signal.signal(signal.SIGUSR2, reboot) # restart and disable debug output

    return log
