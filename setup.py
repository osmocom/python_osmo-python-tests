#!/usr/bin/env python
# Osmopython: test utilities for osmocom programs
# Copyright (C) 2013 Katerina Barone-Adesi kat.obsc@gmail.com

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.

# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from setuptools import setup, find_packages
from osmopy import __version__
import sys

if sys.version_info.major == 2:
	scripts = ["scripts/osmodumpdoc.py",  "scripts/osmotestconfig.py",
	           "scripts/osmotestvty.py"]
elif sys.version_info.major == 3:
	scripts = ["scripts/osmodumpdoc.py",
                   "scripts/osmotestconfig.py",
                   "scripts/osmo_interact_vty.py",
		   "scripts/osmo_interact_ctrl.py",
                   "scripts/osmo_ctrl.py",
		   "scripts/soap.py",
		   "scripts/twisted_ipa.py",
		   "scripts/osmo_verify_transcript_vty.py",
		   "scripts/osmo_verify_transcript_ctrl.py"]

setup(
    name = 'osmopython',
    version = __version__,
    packages = find_packages(),
    scripts = scripts,
    license = "AGPLv3",
    description = "Osmopython: osmocom testing scripts",
    author = "Katerina Barone-Adesi",
    author_email = "kat.obsc@gmail.com"
)
