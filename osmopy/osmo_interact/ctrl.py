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
Run CTRL commands or test transcripts against a given application.  Commandline
invocation exposes only direct command piping, the transcript verification code
is exposed as commandline args by osmo_verify_transcript_ctrl.py.
'''

import re

from .common import *
from osmopy.osmo_ipa import Ctrl, IPA

class InteractCtrl(Interact):
    next_id = 1
    keep_ids = True
    re_command = re.compile(r'^(SET|GET) ([^ ]*) (.*)$')

    class CtrlStep(Interact.StepBase):

        @staticmethod
        def is_next_step(line, interact_instance):
            m = InteractCtrl.re_command.match(line)
            if not m:
                return None
            next_step = InteractCtrl.CtrlStep()

            set_get = m.group(1)
            cmd_id = m.group(2)
            var_val = m.group(3)
            if not interact_instance.keep_ids:
                cmd_id = interact_instance.next_id
                interact_instance.next_id += 1
            next_step.command = '%s %s %s' % (set_get, cmd_id, var_val)

            return next_step

    def __init__(self, port, host, verbose=False, update=False, keep_ids=True):
        if not update:
            keep_ids = True
        self.keep_ids = keep_ids
        super().__init__(InteractCtrl.CtrlStep, port=port, host=host, verbose=verbose, update=update)

    def connect(self):
        self.next_id = 1
        super().connect()

    def send(self, data):
        data = Ctrl().add_header(data)
        return self.socket.send(data) == len(data)

    def receive(self):
        responses = []
        data = self.socket.recv(4096)
        while (len(data)>0):
            (response_with_header, data) = IPA().split_combined(data)
            response = Ctrl().rem_header(response_with_header)
            responses.append(response.decode('utf-8'))
        return responses

    def command(self, command):
        assert self.send(command)
        res = self.receive()
        split_responses = []
        for r in res:
            split_responses.extend(r.splitlines())
        sys.stdout.flush()
        sys.stderr.flush()
        return split_responses

def main_interact_ctrl():
    '''
Run CTRL commands against a given application by stdin/stdout piping.

Optionally, this can launch and tear down the application with -r.

For example, to start a session that allows typing CTRL commands on stdin:

  osmo_interact_ctrl.py -p 4259 \\
    -r 'osmo-hlr -c /etc/osmocom/osmo-hlr.cfg -l /tmp/hlr.db'

Where 4259 is OsmoHLR's CTRL port number, see
https://osmocom.org/projects/cellular-infrastructure/wiki/Port_Numbers

If osmo-hlr is already running, this shortens to just

  osmo_interact_ctrl.py -p 4259

See also osmo_verify_transcript_vty.py, which allows verifying and updating
complete CTRL session transcripts, in essence to write CTRL tests from a screen
dump of a CTRL session.

A VTY equivalent is osmo_interact_vty.py.
'''
    parser = common_parser(__doc__)
    parser_add_run_args(parser)
    args = parser.parse_args()

    interact = InteractCtrl(args.port, args.host, verbose=False, update=False,
                            keep_ids=True)

    main_run_commands(args.run_app_str, args.output_path, args.cmd_str,
                      args.cmd_files, interact)


def main_verify_transcript_ctrl():
    '''
A CTRL transcript contains CTRL commands and their expected results.
It looks like:

"
SET 1 var val
SET_REPLY 1 var OK

GET 2 var
GET_REPLY 2 var val
"

Optionally, this can launch and tear down the application with -r.

For example, if above transcript example is in file test.ctrl, you can verify
that OsmoHLR still shows this behavior by:

  osmo_interact_ctrl.py -p 4259 \\
    -r 'osmo-hlr -c /etc/osmocom/osmo-hlr.cfg -l /tmp/hlr.db' \\
    test.ctrl

Where 4259 is OsmoHLR's CTRL port number, see
https://osmocom.org/projects/cellular-infrastructure/wiki/Port_Numbers

If osmo-hlr is already running, this shortens to just

  osmo_interact_ctrl.py -p 4259 test.ctrl

If osmo-hlr has changed its behavior, e.g. some reply changed, the transcript
can be automatically updated, which overwrites the file, like:

  osmo_interact_ctrl.py -p 4259 -u test.ctrl

See also osmo_interact_ctrl.py, which allows piping CTRL commands to stdin.

A VTY equivalent is osmo_verify_transcript_vty.py.
'''
    parser = common_parser(__doc__)
    parser_add_verify_args(parser)
    parser.add_argument('-i', '--keep-ids', dest='keep_ids', action='store_true',
                        help='With --update, default is to overwrite the command IDs'
                        ' so that they are consecutive numbers starting from 1.'
                        ' With --keep-ids, do not change these command IDs.')
    args = parser.parse_args()

    interact = InteractCtrl(args.port, args.host, args.verbose, args.update, args.keep_ids)

    main_verify_transcripts(args.run_app_str, args.transcript_files, interact, args.verbose)

# vim: tabstop=4 shiftwidth=4 expandtab nocin ai
