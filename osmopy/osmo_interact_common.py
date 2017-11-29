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
Common code for osmo_interact_vty.py and osmo_interact_ctrl.py.
This implements all of application interaction, piping and verification.
osmo_interact_{vty,ctrl}.py plug VTY and CTRL interface specific bits.
'''

import argparse
import sys
import os
import subprocess
import time
import traceback
import socket
import shlex
import re


class Interact:

    class StepBase:
        command = None
        result = None
        leading_blanks = None

        def __init__(self):
            self.result = []

        def verify_interact_state(self, interact_instance):
            # for example to verify that the last VTY prompt received shows the
            # right node.
            pass

        def command_str(self, interact_instance=None):
            return self.command

        def __str__(self):
            return '%s\n%s' % (self.command_str(), '\n'.join(self.result))

        @staticmethod
        def is_next_step(line, interact_instance):
            assert not "implemented by InteractVty.VtyStep and InteractCtrl.CtrlStep"

    socket = None

    def __init__(self, step_class, port, host, verbose=False, update=False):
        '''
        host is the hostname to connect to.
        port is the CTRL port to connect on.
        '''
        self.Step = step_class
        self.port = port
        self.host = host
        self.verbose = verbose
        self.update = update

        if not port:
            raise Exception("You need to provide port number to connect to")

    def connect(self):
        assert self.socket is None
        retries = 30
        took = 0
        while True:
            took += 1
            try:
                self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.socket.setblocking(1)
                self.socket.connect((self.host, int(self.port)))
            except IOError:
                retries -= 1
                if retries <= 0:
                    raise
                time.sleep(.1)
                continue
            break

    def close(self):
        if self.socket is None:
            return
        self.socket.close()
        self.socket = None

    def command(self, command):
        assert not "implemented separately by InteractVty and InteractCtrl"

    def verify_transcript_file(self, transcript_file):
        with open(transcript_file, 'r') as f:
            content = f.read()

        try:
            result = self.verify_transcript(content)
        except:
            print('Error while verifying transcript file %r' % transcript_file, file=sys.stderr)
            sys.stderr.flush()
            raise

        if not self.update:
            return
        content = '\n'.join(result)
        with open(transcript_file, 'w') as f:
            f.write(content)

    def verify_transcript(self, transcript):
        ''''
        transcript is a "screenshot" of a session, a multi-line string
        including commands and expected results.
        Feed commands to self.command() and verify the expected results.
        '''

        # parse steps
        steps = []
        step = None
        blank_lines = 0
        for line in transcript.splitlines():
            if not line:
                blank_lines += 1
                continue
            next_step_started = self.Step.is_next_step(line, self)
            if next_step_started:
                if step:
                    steps.append(step)
                step = next_step_started
                step.leading_blanks = blank_lines
                blank_lines = 0
            elif step:
                # we only count blank lines directly preceding the start of a
                # next step. Insert blank lines in the middle of a response
                # back into the response:
                if blank_lines:
                    step.result.extend([''] * blank_lines)
                blank_lines = 0
                step.result.append(line)
        if step:
            steps.append(step)
        step = None

        actual_result = []

        # run steps
        step_nr = 0
        for step in steps:
            step_nr += 1
            try:
                if self.verbose:
                    if step.leading_blanks:
                        print('\n' * step.leading_blanks, end='')
                    print(step.command_str())
                    sys.stdout.flush()

                step.verify_interact_state(self)

                res = self.command(step.command)

                if self.verbose:
                    sys.stderr.flush()
                    sys.stdout.flush()
                    print('\n'.join(res))
                    sys.stdout.flush()

                if step.leading_blanks:
                    actual_result.extend([''] * step.leading_blanks)
                actual_result.append(step.command_str(self))

                match_result = self.match_lines(step.result, res)

                if self.update:
                    if match_result is True:
                        # preserve any wildcards
                        actual_result.extend(step.result)
                    else:
                        # mismatch, take exactly what came in
                        actual_result.extend(res)
                    continue
                if match_result is not True:
                    raise Exception('Result mismatch:\n%s\n\nExpected:\n[\n%s\n]\n\nGot:\n[\n%s\n%s\n]'
                                    % (match_result, step, step.command_str(), '\n'.join(res)))
            except:
                print('Error during transcript step %d:\n[\n%s\n]' % (step_nr, step),
                      file=sys.stderr)
                sys.stderr.flush()
                raise

        # final line ending
        actual_result.append('')
        return actual_result

    @staticmethod
    def match_lines(expect, got):
        '''
        Match two lists of strings, allowing certain wildcards:
        - In 'expect', if a line is exactly '...', it matches any number of
          arbitrary lines in 'got'; the implementation is trivial and skips
          lines to the first occurence in 'got' that continues after '...'.
        - If an 'expect' line is '... !regex', it matches any number of
          lines like '...', but the given regex must not match any of those
          lines.

        Return 'True' on match, or a string describing the mismatch.
        '''
        def match_line(expect_line, got_line):
            return expect_line == got_line

        ANY = '...'
        ANY_EXCEPT = '... !'

        e = 0
        g = 0
        while e < len(expect):
            if expect[e] == ANY or expect[e].startswith(ANY_EXCEPT):
                wildcard = expect[e]
                e += 1
                g_end = g

                if e >= len(expect):
                    # anything left in 'got' is accepted.
                    g_end = len(got)

                # look for the next occurence of the expected line in 'got'
                while g_end < len(got) and not match_line(expect[e], got[g_end]):
                    g_end += 1

                if wildcard == ANY:
                    # no restrictions on lines
                    g = g_end

                elif wildcard.startswith(ANY_EXCEPT):
                    except_re = re.compile(wildcard[len(ANY_EXCEPT):])
                    while g < g_end:
                        if except_re.search(got[g]):
                          return ('Got forbidden line for wildcard %r:'
                                  ' did not expect %r in line %d of response'
                                  % (wildcard, got[g], g))
                        g += 1

                continue

            if g >= len(got):
                return 'Cannot find line %r' % expect[e]

            if not match_line(expect[e], got[g]):
                return 'Mismatch:\nExpect:\n%r\nGot:\n%r' % (expect[e], got[g])

            e += 1
            g += 1

        if g < len(got):
            return 'Did not expect line %r' % got[g]
        return True

    def feed_commands(self, output, command_strs):
        for command_str in command_strs:
            for command in command_str.splitlines():
                res = self.command(command)
                output.write('\n'.join(res))
                output.write('\n')

def end_process(proc, quiet=False):
    if not proc:
        return

    rc = proc.poll()
    if rc is not None:
        if not quiet:
            print('Process has already terminated with', rc)
        proc.wait()
        return

    proc.terminate()
    time_to_wait_for_term = 5
    wait_step = 0.001
    waited_time = 0
    while True:
        # poll returns None if proc is still running
        if proc.poll() is not None:
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
        if not quiet:
            print("Killed child process")
    elif waited_time > .002:
        if not quiet:
            print("Terminating took %.3fs" % waited_time)
    proc.wait()

class Application:
    proc = None
    _devnull = None

    @staticmethod
    def devnull():
        if Application._devnull is None:
            Application._devnull = open(os.devnull, 'w')
        return Application._devnull

    def __init__(self, run_app_str, purge_output=True, quiet=False):
        self.command_tuple = shlex.split(run_app_str)
        self.purge_output = purge_output
        self.quiet = quiet

    def run(self):
        out_err = None
        if self.purge_output:
            out_err = Application.devnull()

        if not self.quiet:
            print('Launching: cd %r; %s' % (os.getcwd(), ' '.join(self.command_tuple)))
        self.proc = subprocess.Popen(self.command_tuple, stdout=out_err, stderr=out_err)

    def stop(self):
        end_process(self.proc, self.quiet)

def verify_application(run_app_str, interact, transcript_file, verbose):
    passed = None
    application = None

    sys.stdout.flush()
    sys.stderr.flush()

    if run_app_str:
        application = Application(run_app_str, purge_output=not verbose)
        application.run()

    try:
        interact.connect()
        interact.verify_transcript_file(transcript_file)
        passed = True
    except:
        traceback.print_exc()
        passed = False
    interact.close()

    if application:
        application.stop()

    sys.stdout.flush()
    sys.stderr.flush()

    return passed

def common_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument('-r', '--run', dest='run_app_str',
                        help='command to run to launch application to test,'
                        ' including command line arguments. If omitted, no'
                        ' application is launched.')
    parser.add_argument('-p', '--port', dest='port',
                        help="Port to reach the application at.")
    parser.add_argument('-H', '--host', dest='host', default='localhost',
                        help="Host to reach the application at.")
    return parser

def parser_add_verify_args(parser):
    parser.add_argument('-u', '--update', dest='update', action='store_true',
                        help='Do not verify, but OVERWRITE transcripts based on'
                        ' the application\'s current behavior. OVERWRITES TRANSCRIPT'
                        ' FILES.')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Print commands and application output')
    parser.add_argument('transcript_files', nargs='*', help='transcript file(s) to verify')
    return parser

def parser_add_run_args(parser):
    parser.add_argument('-O', '--output', dest='output_path',
                        help="Write command results to a file instead of stdout."
                        "('-O -' writes to stdout and is the default)")
    parser.add_argument('-c', '--command', dest='cmd_str',
                        help="Run this command (before reading input files, if any)."
                        " multiple commands may be separated by ';'")
    parser.add_argument('cmd_files', nargs='*', help='file(s) with plain commands to run')
    return parser

def main_run_commands(run_app_str, output_path, cmd_str, cmd_files, interact):
    to_stdout = False
    if not output_path or output_path == '-':
        to_stdout = True
        output = sys.stdout
    else:
        output = open(output_path, 'w')

    application = None

    if run_app_str:
        application = Application(run_app_str, quiet=to_stdout)
        application.run()

    try:
        interact.connect()

        if cmd_str:
            interact.feed_commands(output, cmd_str.split(';'))

        for f_path in (cmd_files or []):
            with open(f_path, 'r') as f:
                interact.feed_commands(output, f.read().decode('utf-8').splitlines())

        if not (cmd_str or cmd_files):
            while True:
                line = sys.stdin.readline()
                if not line:
                    break;
                interact.feed_commands(output, line.split(';'))
    except:
        traceback.print_exc()
    finally:
        if not to_stdout:
            try:
                output.close()
            except:
                traceback.print_exc()

        try:
            interact.close()
        except:
            traceback.print_exc()

        if application:
            try:
                application.stop()
            except:
                traceback.print_exc()

def main_verify_transcripts(run_app_str, transcript_files, interact, verbose):
    results = []
    for t in transcript_files:
        passed = verify_application(run_app_str=run_app_str,
                                    interact=interact,
                                    transcript_file=t,
                                    verbose=verbose)
        results.append((passed, t))

    print('\nRESULTS:')
    all_passed = True
    for passed, t in results:
        print('%s: %s' % ('pass' if passed else 'FAIL', t))
        all_passed = all_passed and passed
    print()

    if not all_passed:
        sys.exit(1)

# vim: tabstop=4 shiftwidth=4 expandtab nocin ai
