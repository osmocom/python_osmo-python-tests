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

import time
import unittest

import osmopy.obscvty as obscvty
import osmopy.osmoutil as osmoutil

"""Test a VTY. Warning: osmoappdesc must be imported first."""


class TestVTY(unittest.TestCase):
    def setUp(self):
        osmo_vty_cmd = osmoappdesc.vty_command
        try:
            self.proc = osmoutil.popen_devnull(osmo_vty_cmd)
        except OSError:
            print >> sys.stderr, "Current directory: %s" % os.getcwd()
            print >> sys.stderr, "Consider setting -w"
        time.sleep(1)

        appstring = osmoappdesc.vty_app[2]
        appport = osmoappdesc.vty_app[0]
        self.vty = obscvty.VTYInteract(appstring, "127.0.0.1", appport)

    def tearDown(self):
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

    workdir = "."
    confpath = "."

    parser = argparse.ArgumentParser()
    parser.add_argument("-p", "--pythonconfpath", dest="p",
                        help="searchpath for config")
    parser.add_argument("-w", "--workdir", dest="w",
                        help="Working directory to run in")
    args = parser.parse_args()

    if args.w:
        workdir = args.w

    if args.p:
        confpath = args.p
    osmoappdesc = None
    try:
        osmoappdesc = osmoutil.importappconf(confpath, "osmoappdesc")
    except ImportError as e:
        print >> sys.stderr, "osmoappdesc not found, set searchpath with -p"
        sys.exit(1)

    os.chdir(workdir)
    suite = unittest.TestLoader().loadTestsFromTestCase(TestVTY)
    res = unittest.TextTestRunner(verbosity=1).run(suite)
    sys.exit(len(res.errors) + len(res.failures))
