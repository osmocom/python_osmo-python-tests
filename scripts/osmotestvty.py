#!/usr/bin/env python

# (C) 2013 by Katerina Barone-Adesi <kat.obsc@gmail.com>
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import os
import time
import unittest

import osmopy.obscvty as obscvty
import osmopy.osmoutil as osmoutil

confpath = '.'

"""Test a VTY. Warning: osmoappdesc must be imported first."""


class TestVTY(unittest.TestCase):

    def setUp(self):
        osmo_vty_cmd = osmoappdesc.vty_command[:]
        config_index = osmo_vty_cmd.index('-c')
        if config_index:
            cfi = config_index + 1
            osmo_vty_cmd[cfi] = os.path.join(confpath, osmo_vty_cmd[cfi])

        try:
            print "Launch: %s from %s" % (' '.join(osmo_vty_cmd), os.getcwd())
            self.proc = osmoutil.popen_devnull(osmo_vty_cmd)
        except OSError:
            print >> sys.stderr, "Current directory: %s" % os.getcwd()
            print >> sys.stderr, "Consider setting -b"

        appstring = osmoappdesc.vty_app[2]
        appport = osmoappdesc.vty_app[0]
        self.vty = obscvty.VTYInteract(appstring, "127.0.0.1", appport)

    def tearDown(self):
        self.vty._close_socket()
        self.vty = None
        osmoutil.end_proc(self.proc)

    def test_history(self):
        t1 = "show version"
        self.vty.command(t1)
        test_str = "show history"
        assert(self.vty.w_verify(test_str, [t1]))

    def test_unknown_command(self):
        test_str = "help show"
        assert(self.vty.verify(test_str, ['% Unknown command.']))

    def test_terminal_length(self):
        test_str = "terminal length 20"
        assert(self.vty.verify(test_str, ['']))


if __name__ == '__main__':
    import argparse
    import os
    import sys

    workdir = '.'

    parser = argparse.ArgumentParser()
    parser.add_argument("-v", "--verbose", dest="verbose",
                        action="store_true", help="verbose mode")
    parser.add_argument("-p", "--pythonconfpath", dest="p",
                        help="searchpath for config")
    parser.add_argument("-w", "--workdir", dest="w",
                        help="Working directory")
    args = parser.parse_args()

    verbose_level = 1
    if args.verbose:
        verbose_level = 2

    if args.w:
        workdir = args.w

    if args.p:
        confpath = args.p
    osmoappdesc = osmoutil.importappconf_or_quit(confpath, "osmoappdesc",
                                                 args.p)

    print "confpath %s, workdir %s" % (confpath, workdir)
    os.chdir(workdir)
    print "Running tests for specific VTY commands"
    suite = unittest.TestLoader().loadTestsFromTestCase(TestVTY)
    res = unittest.TextTestRunner(verbosity=verbose_level).run(suite)
    sys.exit(len(res.errors) + len(res.failures))
