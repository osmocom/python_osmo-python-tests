#!/usr/bin/python3
# -*- mode: python-mode; py-indent-tabs-mode: nil -*-
"""
/*
 * Copyright (C) 2017 sysmocom s.f.m.c. GmbH
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

from osmopy.osmo_ipa import Ctrl
import socket, argparse, sys, logging, csv

__version__ = "0.0.1" # bump this on every non-trivial change

def connect(host, port):
        sck = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sck.setblocking(1)
        sck.connect((host, port))
        return sck

def get_var(sck, var):
        (_, c) = Ctrl().cmd(var, None)
        sck.send(c)
        return Ctrl().parse_kv(sck.recv(4096))

def get_interval(group_name, group_counters, interval):
        log.debug('Getting %s counter values: %s...' % (group_name, interval))
        (_, c) = get_var(sock, 'rate_ctr.%s.%s' % (interval, group_name))
        for ctr in c.split(';'):
                if len(ctr):
                        (k, v) = ctr.split()
                        group_counters[k] = group_counters.get(k, (group_name,)) + (v,)
        return len(group_counters)


if __name__ == '__main__':
        p = argparse.ArgumentParser(description='Dump rate counters into csv via Osmocom CTRL protocol.')
        p.add_argument('-v', '--version', action='version', version=("%(prog)s v" + __version__))
        p.add_argument('-p', '--port', type=int, default=4249, help="Port to use for CTRL interface, defaults to 4249")
        p.add_argument('-c', '--ctrl', default='localhost', help="Adress to use for CTRL interface, defaults to localhost")
        p.add_argument('-d', '--debug', action='store_true', help="Enable debug log")
        p.add_argument('--header', action='store_true', help="Prepend column header to output")
        p.add_argument('-o', '--output', nargs='?', type=argparse.FileType('w'), default=sys.stdout, help="Output file, defaults to stdout")
        args = p.parse_args()

        log = logging.getLogger('rate_ctr2csv')
        log.setLevel(logging.DEBUG if args.debug else logging.INFO)
        log.addHandler(logging.StreamHandler(sys.stderr))

        log.info('Connecting to %s:%d...' % (args.ctrl, args.port))
        sock = connect(args.ctrl, args.port)

        log.info('Getting rate counter groups info...')
        (_, g) = get_var(sock, 'rate_ctr.*')

        w = csv.writer(args.output, dialect='unix')
        total_groups = 0
        total_rows = 0

        if args.header:
                w.writerow(['group', 'counter', 'absolute', 'second', 'minute', 'hour', 'day'])

        for group in g.split(';'):
                if len(group):
                        g_counters = {}
                        total_groups += 1
                        total_rows += list(map(lambda x: get_interval(group, g_counters, x), ('abs', 'per_sec', 'per_min', 'per_hour', 'per_day')))[0]
                        for (k, (gr, absolute, per_sec, per_min, per_hour, per_day)) in g_counters.items():
                                w.writerow([gr, k, absolute, per_sec, per_min, per_hour, per_day])

        log.info('Completed: %d counters from %d groups received.' % (total_rows, total_groups))
