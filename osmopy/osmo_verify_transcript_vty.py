#!/usr/bin/env python3
#
# (C) 2017 by sysmocom s.f.m.c. GmbH <info@sysmocom.de>
# All rights reserved.
#
# Author: Neels Hofmeyr <nhofmeyr@sysmocom.de>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

'''
Run VTY test transcripts against a given application.

A VTY transcript contains VTY commands and their expected results.
It looks like:

"
OsmoHLR> enable

OsmoHLR# subscriber show imsi 123456789023000
% No subscriber for imsi = '123456789023000'
OsmoHLR# subscriber show msisdn 12345
% No subscriber for msisdn = '12345'

OsmoHLR# subscriber create imsi 123456789023000
% Created subscriber 123456789023000
    ID: 1
    IMSI: 123456789023000
    MSISDN: none
    No auth data
"

The application to be tested is described by
- a binary to run,
- command line arguments to pass to the binary,
- the VTY telnet port,
- the application name as printed in the VTY prompt.

This module can either be run directly to run or update a given VTY transcript,
or it can be imported as a module to run more complex setups.
'''

import re

from osmopy.osmo_interact_vty import *

if __name__ == '__main__':
    parser = common_parser()
    parser_add_vty_args(parser)
    parser_add_verify_args(parser)
    args = parser.parse_args()

    interact = InteractVty(args.prompt, args.port, args.host, args.verbose, args.update)

    main_verify_transcripts(args.run_app_str, args.transcript_files, interact, args.verbose)

# vim: tabstop=4 shiftwidth=4 expandtab nocin ai
