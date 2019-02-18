#!/usr/bin/env python3
#
# (C) 2019 by sysmocom s.f.m.c. GmbH <info@sysmocom.de>
# All rights reserved.
#
# Author: Oliver Smith <osmith@sysmocom.de>
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
#
# SPDX-License-Identifier: GPL-3.0-or-later

'''
Wait until a given application listens for TCP connections, then run C tests or
other programs against it.
'''

import subprocess
from .common import *

class InteractExec(Interact):
    def __init__(self, port, verbose=False, update=False):
        super().__init__(Interact.StepBase, host="localhost", port=port,
                         verbose=verbose, update=update)

    def command(self, command):
        print("Launching: " + command)

        try:
            # Do not allow commands with arguments, as these would behave
            # unexpectedly: the commands get split by ';', no matter if in
            # quotes or not.
            output = subprocess.check_output([command],
                                             stderr=subprocess.STDOUT)
            output = output.decode("utf-8")
        except subprocess.CalledProcessError as e:
            # Print output on error too
            print(e.output.decode("utf-8"))
            print("---")
            sys.stdout.flush()
            sys.stderr.flush()
            raise

        print(output)
        sys.stdout.flush()
        sys.stderr.flush()
        return ("$ " + command + "\n" + output).split("\n")

def main_interact_exec():
    '''
Wait until a given application listens for TCP connections, then run C tests or
other programs against it.

Example:
  osmo_interact_exec.py \\
    -r 'osmo-hlr -c /etc/osmocom/osmo-hlr.cfg -l /tmp/hlr.db' \\
    -p 4222 \\
    -c 'tests/gsup_client_session/gsup_client_session_test'
'''
    parser = common_parser(main_interact_exec.__doc__, host=False)
    parser_add_run_args(parser, cmd_files=False)
    parser_require_args(parser, ("run_app_str", "port", "cmd_str"))
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='print run command (from -r) output')
    args = parser.parse_args()

    interact = InteractExec(args.port, verbose=args.verbose, update=False)

    main_run_commands(args.run_app_str, args.output_path, args.cmd_str,
                      cmd_files=[], interact=interact,
                      purge_output=not args.verbose)


# vim: tabstop=4 shiftwidth=4 expandtab nocin ai
