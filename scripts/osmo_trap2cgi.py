#!/usr/bin/env python3
# -*- mode: python-mode; py-indent-tabs-mode: nil -*-
"""
/*
 * Copyright (C) 2019 sysmocom s.f.m.c. GmbH
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

__version__ = "0.0.2" # bump this on every non-trivial change

from functools import partial
import configparser, argparse, time, os, asyncio, aiohttp
from osmopy.trap_helper import make_params, gen_hash, log_init, comm_proc
from osmopy.osmo_ipa import Ctrl


def log_bsc_time(l, rq, task, ts, bsc, msg, *args, **kwargs):
    """
    Logging contextual wrapper.
    FIXME: remove task parameter once we bump requirements to Python 3.7+
    """
    # FIXME: following function is deprecated and will be removed in Python 3.9
    # Use the asyncio.all_tasks() function instead when available (Python 3.7+).
    num_tasks = len(task.all_tasks())
    num_req = len(rq)
    delta = time.perf_counter() - ts
    if delta < 1:
        l('[%d/%d] BSC %s: ' + msg, num_req, num_tasks, bsc, *args, **kwargs)
    else:
        l('[%d/%d] BSC %s, %.2f sec: ' + msg, num_req, num_tasks, bsc, time.perf_counter() - ts, *args, **kwargs)

def check_h_val(ctrl, h, v, t, exp):
    """
    Check for header inconsistencies.
    """
    if v != exp:
        ctrl.log.error('Unexpected %s value %x (instead of %x) in |%s| header', t, v, exp, h.hex())

def get_ctrl_len(ctrl, header):
    """
    Obtain expected message length.
    """
    (dlen, p, e, _) = ctrl.del_header(header)
    check_h_val(ctrl, header, p, "protocol", ctrl.PROTO['OSMO'])
    check_h_val(ctrl, header, e, "extension", ctrl.EXT['CTRL'])
    return dlen - 1


class Proxy(Ctrl):
    """
    Wrapper class to implement per-type message dispatch and keep BSC <-> http Task mapping.
    N. B: keep async/await semantics out of it.
    """
    def __init__(self, log):
        super().__init__()
        self.req = {}
        self.log = log
        self.conf = configparser.ConfigParser(interpolation = None)
        self.conf.read(self.config_file)
        self.timeout = self.conf['main'].getint('timeout', 30)
        self.location = self.conf['main'].get('location')
        self.ctrl_addr = self.conf['main'].get('addr_ctrl', 'localhost')
        self.ctrl_port = self.conf['main'].getint('port_ctrl', 4250)
        self.concurrency = self.conf['main'].getint('num_max_conn', 5)
        # FIXME: use timeout parameter when available (aiohttp version 3.3) as follows
        #self.http_client = aiohttp.ClientSession(connector = aiohttp.TCPConnector(limit = self.concurrency), timeout = self.timeout)
        self.http_client = aiohttp.ClientSession(connector = aiohttp.TCPConnector(limit = self.concurrency))

    def dispatch(self, w, data):
        """
        Basic dispatcher: the expected entry point for CTRL messages.
        """
        (cmd, _, v) = data.decode('utf-8').split(' ', 2)
        method = getattr(self, cmd, lambda *_: self.log.info('CTRL %s is unhandled by dispatch: ignored.', cmd))
        method(w, v.split())

    def ERROR(self, _, k):
        """
        Handle CTRL ERROR messages.
        """
        self.log_ignore('ERROR', k)

    def SET_REPLY(self, _, k):
        """
        Handle CTRL SET_REPLY messages.
        """
        self.log_ignore('SET_REPLY', k)

    def TRAP(self, w, k):
        """
        Handle incoming TRAPs.
        """
        p = k[0].split('.')
        if p[-1] == 'location-state':
            self.handle_locationstate(w, p[1], p[3], p[5], k[1])
        else:
            self.log_ignore('TRAP', k[0])

    def handle_locationstate(self, w, net, bsc, bts, data):
        """
        Handle location-state TRAP: parse trap content, build HTTP request and setup async handlers.
        """
        ts = time.perf_counter()
        self.cleanup_task(bsc)
        params = make_params(bsc, data)
        params['h'] = gen_hash(params, self.conf['main'].get('secret_key'))
        # FIXME: use asyncio.create_task() when available (Python 3.7+).
        t = asyncio.ensure_future(self.http_client.post(self.location, data = params))
        log_bsc_time(self.log.info, self.req, t, ts, bsc, 'location-state@%s => %s', params['time_stamp'], data)
        t.add_done_callback(partial(self.reply_callback, w, bsc, ts))
        self.req[bsc] = (t, ts)
        log_bsc_time(self.log.info, self.req, t, ts, bsc, 'request added (net %s, BTS %s)', net, bts)

    def cleanup_task(self, bsc):
        """
        It's ok to cancel() task which is done()
        but if either of the checks above fires it means that Proxy() is in inconsistent state
        which should never happen as long as we keep async/await semantics out of it.
        """
        if bsc in self.req:
            (task, ts) = self.req[bsc]
            log_bsc = partial(log_bsc_time, self.log.error, self.req, task, ts, bsc)
            if task.done():
                log_bsc('task is done but not removed')
            if task.cancelled():
                log_bsc('task is cancelled without update')
            task.cancel()

    def log_ignore(self, kind, m):
        """
        Log ignored CTRL message.
        """
        self.log.error('Ignoring CTRL %s: %s', kind, ' '.join(m) if type(m) is list else m)

    def reply_callback(self, w, bsc, ts, task):
        """
        Process per-BSC response status and prepare async handler if necessary.
        We don't have to delete cancel()ed task from self.req explicitly because it will be replaced by new one in handle_locationstate()
        """
        log_bsc = partial(log_bsc_time, self.log.info, self.req, task, ts, bsc)
        if task.cancelled():
            log_bsc('request cancelled')
        else:
            exp = task.exception()
            if exp:
                log_bsc('exception %s triggered', repr(exp))
            else:
                resp = task.result()
                if resp.status != 200:
                    log_bsc('unexpected HTTP response %d', resp.status)
                else:
                    log_bsc('request completed')
                    # FIXME: use asyncio.create_task() when available (Python 3.7+).
                    asyncio.ensure_future(recv_response(self.log, w, bsc, resp.json()))
            del self.req[bsc]


async def recv_response(log, w, bsc, resp):
    """
    Process json response asynchronously.
    """
    js = await resp
    if js.get('error'):
        log.info('BSC %s response error: %s', bsc, repr(js.get('error')))
    else:
        comm_proc(js.get('commands'), bsc, w.write, log)
        await w.drain() # Trigger Writer's flow control

async def recon_reader(proxy, reader, num_bytes):
    """
    Read requested amount of bytes, reconnect if necessary.
    """
    try:
        return await reader.readexactly(num_bytes)
    except asyncio.IncompleteReadError:
        proxy.log.info('Failed to read %d bytes reconnecting to %s:%d...', num_bytes, proxy.ctrl_addr, proxy.ctrl_port)
        raise

async def ctrl_client(proxy, rd, wr):
    """
    Read CTRL stream and handle selected messages.
    """
    while True:
        header = await recon_reader(proxy, rd, 4)
        data = await recon_reader(proxy, rd, get_ctrl_len(proxy, header))
        proxy.dispatch(wr, data)

async def conn_client(proxy):
    """
    (Re)establish connection with CTRL server and pass Reader/Writer to CTRL handler.
    """
    while True:
        try:
            reader, writer = await asyncio.open_connection(proxy.ctrl_addr, proxy.ctrl_port)
            proxy.log.info('Connected to %s:%d', proxy.ctrl_addr, proxy.ctrl_port)
            await ctrl_client(proxy, reader, writer)
        except OSError as e:
            proxy.log.info('%s: %d seconds delayed retrying...', e, proxy.timeout)
            await asyncio.sleep(proxy.timeout)
        except asyncio.IncompleteReadError:
            pass
        proxy.log.info('Reconnecting...')


if __name__ == '__main__':
    a = argparse.ArgumentParser(description = 'Proxy between given GCI service and Osmocom CTRL protocol.')
    a.add_argument('-v', '--version', action = 'version', version = ("%(prog)s v" + __version__))
    a.add_argument('-d', '--debug', action = 'store_true', help = "Enable debug log")
    a.add_argument('-c', '--config-file', required = True, help = "Path to mandatory config file (in INI format).")

    P = Proxy(log_init('TRAP2CGI', a.parse_args(namespace=Proxy).debug))

    P.log.info('CGI proxy v%s starting with PID %d:', __version__, os.getpid())
    P.log.info('Destination %s (concurrency %d)', P.location, P.concurrency)
    P.log.info('Connecting to TRAP source %s:%d...', P.ctrl_addr, P.ctrl_port)

    loop = asyncio.get_event_loop()
    loop.run_until_complete(conn_client(P))
    # FIXME: use loop.run() function instead when available (Python 3.7+).
