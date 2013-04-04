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


"""Run a command, with stdout and stderr directed to devnull"""


def popen_devnull(cmd):
    devnull = open(os.devnull, 'w')
    return subprocess.Popen(cmd, stdout=devnull, stderr=devnull)


"""End a process.

If the process doesn't appear to exist (for instance, is None), do nothing"""


def end_proc(proc):
    if proc:
        proc.kill()
        proc.wait()


"""Add a directory to sys.path, try to import a config file.

This may throw ImportError if the config file is not found."""


def importappconf(dirname, confname):
    if dirname not in sys.path:
        sys.path.append(dirname)
    return importlib.import_module(confname)
