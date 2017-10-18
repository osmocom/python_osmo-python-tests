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

from osmopy.osmo_verify_transcript_common import *

class InteractVty(Interact):

    class VtyStep(Interact.StepBase):
        expect_node = None   # e.g. '(config-net)'
        expect_prompt_char = None # '>' or '#'

        def __init__(self, prompt):
            super().__init__()
            self.prompt = prompt

        def verify_interact_state(self, interact_instance):
            if interact_instance.update:
                return
            if interact_instance.this_node != self.expect_node:
                raise Exception('Mismatch: expected VTY node %r in the prompt, got %r'
                                % (self.expect_node, interact_instance.this_node))
            if interact_instance.this_prompt_char != self.expect_prompt_char:
                raise Exception('Mismatch: expected VTY prompt character %r, got %r'
                                % (self.expect_prompt_char, interact_instance.this_prompt_char))

        @staticmethod
        def is_next_step(line, interact_instance):
            m = interact_instance.re_prompt.match(line)
            if not m:
                return None
            next_step = InteractVty.VtyStep(interact_instance.prompt)
            next_step.expect_node = m.group(1)
            next_step.expect_prompt_char = m.group(2)
            next_step.command = m.group(3)
            return next_step

        def command_str(self, interact_instance=None):
            if interact_instance is None:
                node = self.expect_node
                prompt_char = self.expect_prompt_char
            else:
                node = interact_instance.last_node
                prompt_char = interact_instance.last_prompt_char
            if node:
                node = '(%s)' % node
            node = node or ''
            return '%s%s%s %s' % (self.prompt, node, prompt_char, self.command)

    def __init__(self, prompt, port, host, verbose, update):
        self.prompt = prompt
        super().__init__(InteractVty.VtyStep, port, host, verbose, update)

    def connect(self):
        self.this_node = None
        self.this_prompt_char = '>' # slight cheat for initial prompt char
        self.last_node = None
        self.last_prompt_char = None

        super().connect()
        # receive the first welcome message and discard
        data = self.socket.recv(4096)
        if not self.prompt:
            b = data
            b = b[b.rfind(b'\n') + 1:]
            while b and (b[0] < ord('A') or b[0] > ord('z')):
                b = b[1:]
            prompt_str = b.decode('utf-8')
            if '>' in prompt_str:
                self.prompt = prompt_str[:prompt_str.find('>')]
        if not self.prompt:
            raise Exception('Could not find application name; needed to decode prompts.'
                            ' Initial data was: %r' % data)
        self.re_prompt = re.compile('^%s(?:\(([\w-]*)\))?([#>]) (.*)$' % self.prompt)

    def _command(self, command_str, timeout=10):
        self.socket.send(command_str.encode())

        waited_since = time.time()
        received_lines = []
        last_line = ''

        while True:
            new_data = self.socket.recv(4096).decode('utf-8')

            last_line = "%s%s" % (last_line, new_data)

            if last_line:
                lines = last_line.splitlines()
                received_lines.extend(lines[:-1])
                last_line = lines[-1]

            match = self.re_prompt.match(last_line)
            if not match:
                if time.time() - waited_since > timeout:
                    raise IOError("Failed to read data (did the app crash?)")
                time.sleep(.1)
                continue

            self.last_node = self.this_node
            self.last_prompt_char = self.this_prompt_char
            self.this_node = match.group(1) or None
            self.this_prompt_char = match.group(2)
            break

        # expecting to have received the command we sent as echo, remove it
        clean_command_str = command_str.strip()
        if clean_command_str.endswith('?'):
            clean_command_str = clean_command_str[:-1]
        if received_lines and received_lines[0] == clean_command_str:
            received_lines = received_lines[1:]
        return received_lines

    def command(self, command_str, timeout=10):
        command_str = command_str or '\r'
        if command_str[-1] not in '?\r\t':
            command_str = command_str + '\r'

        received_lines = self._command(command_str, timeout)

        if command_str[-1] == '?':
            self._command('\x03', timeout)

        return received_lines

if __name__ == '__main__':
    parser = common_parser()
    parser.add_argument('-n', '--prompt-name', dest='prompt',
                        help="Name used in application's telnet VTY prompt."
                        " If omitted, will attempt to determine the name from"
                        " the initial VTY prompt.")
    args = parser.parse_args()

    interact = InteractVty(args.prompt, args.port, args.host, args.verbose, args.update)

    main(command_str=args.command_str,
         transcript_files=args.transcript_files,
         interact=interact,
         verbose=args.verbose)

# vim: tabstop=4 shiftwidth=4 expandtab nocin ai
