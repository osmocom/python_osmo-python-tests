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

import subprocess
import os
import sys
import importlib
import time
import unittest


"""Run a command, with stdout and stderr directed to devnull"""

devnull = None

def popen_devnull(cmd, verbose=True):
    global devnull
    if devnull is None:
        if verbose:
            print "Opening /dev/null"
        devnull = open(os.devnull, 'w')
    if verbose:
        print "Launching: PWD=%s %s" % (os.getcwd(), ' '.join([repr(c) for c in cmd]))
    return subprocess.Popen(cmd, stdout=devnull, stderr=devnull)


"""End a process.

If the process doesn't appear to exist (for instance, is None), do nothing"""


def end_proc(proc):
    if not proc:
        return

    proc.terminate()
    time_to_wait_for_term = 5
    wait_step = 0.001
    waited_time = 0
    while True:
        # poll returns None if proc is still running
        rc = proc.poll()
        if rc is not None:
            break
        waited_time += wait_step
        # make wait_step approach 1.0
        wait_step = (1. + 5. * wait_step) / 6.
        if waited_time >= time_to_wait_for_term:
            break
        time.sleep(wait_step)

    if proc.poll() is None:
        # termination seems to be slower than that, let's just kill
        proc.kill()
        print "Killed child process"
    elif waited_time > .002:
        print "Terminating took %.3fs" % waited_time
    proc.wait()


"""Add a directory to sys.path, try to import a config file."""

def importappconf_or_quit(dirname, confname, p_set):
    if dirname not in sys.path:
        sys.path.append(dirname)
    try:
        return importlib.import_module(confname)
    except ImportError as e:
        if p_set:
            print >> sys.stderr, "osmoappdesc not found in %s" % dirname
        else:
            print >> sys.stderr, "set osmoappdesc location with -p <dir>"
        sys.exit(1)


def pick_tests(suite, *name_snippets):
    '''for unittest: Non-standard way of picking only selected tests to run,
       by name.  Kind of stupid of python unittest to not provide this feature
       more easily.'''

    new_tests = []
    for t in suite._tests:
        if isinstance(t, unittest.suite.TestSuite):
            pick_tests(t, *name_snippets)
            new_tests.append(t)
            continue

        if not isinstance(t, unittest.TestCase):
            new_tests.append(t)
            continue

        if any([n.lower() in t._testMethodName.lower() for n in name_snippets]):
            new_tests.append(t)
    suite._tests = new_tests
