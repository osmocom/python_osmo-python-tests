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
Run CTRL test transcripts against a given application.

A CTRL transcript contains CTRL commands and their expected results.
It looks like:

"
SET 1 var val
SET_REPLY 1 var OK
GET 2 var
GET_REPLY 2 var val
"

The application to be tested is described by
- a binary to run,
- command line arguments to pass to the binary,
- the CTRL port.

This module can either be run directly to run or update a given CTRL transcript,
or it can be imported as a module to run more complex setups.
'''

from osmopy.osmo_interact_ctrl import *

if __name__ == '__main__':
    parser = common_parser()
    parser_add_verify_args(parser)
    parser.add_argument('-i', '--keep-ids', dest='keep_ids', action='store_true',
                        help='With --update, default is to overwrite the command IDs'
                        ' so that they are consecutive numbers starting from 1.'
                        ' With --keep-ids, do not change these command IDs.')
    args = parser.parse_args()

    interact = InteractCtrl(args.port, args.host, args.verbose, args.update, args.keep_ids)

    main_verify_transcripts(args.run_app_str, args.transcript_files, interact, args.verbose)

# vim: tabstop=4 shiftwidth=4 expandtab nocin ai
