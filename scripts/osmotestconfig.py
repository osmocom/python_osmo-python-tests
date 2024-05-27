#!/usr/bin/env python3

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
import os
import os.path
import shutil
import time
import sys, shutil, stat
import tempfile

import osmopy.obscvty as obscvty
import osmopy.osmoutil as osmoutil


# Run all tests for a given config, raise error on failure
def test_config(app_desc, config, tmpdir, verbose=True):
    if test_config_atest(app_desc, config, verify_doc, verbose)[0] > 0:
        raise RuntimeError(f"{config}: verify_doc() failed")

    newconfig = copy_config(tmpdir, config)
    if test_config_atest(app_desc, newconfig, write_config, verbose) > 0:
        raise RuntimeError(f"{config}: write_config() failed")

    if test_config_atest(app_desc, newconfig, token_vty_command, verbose) > 0:
        raise RuntimeError(f"{config}: token_vty_command() failed")


def test_config_atest(app_desc, config, run_test, verbose=True):
    proc = None
    ret = None
    vty = None
    try:
        cmd = app_desc[1].split(' ') + [ "-c", config]
        if verbose:
            print("Verifying %s, test %s" % (' '.join(cmd), run_test.__name__))

        proc = osmoutil.popen_devnull(cmd)
        end = app_desc[2]
        port = app_desc[0]
        vty = obscvty.VTYInteract(end, "127.0.0.1", port)
        ret = run_test(vty)

    except IOError as se:
        print("Failed to verify %s" % ' '.join(cmd), file=sys.stderr)
        print("Current directory: %s" % os.getcwd(), file=sys.stderr)
        print("Error was %s" % se, file=sys.stderr)
        print("Config was\n%s" % open(config).read(), file=sys.stderr)
        raise se

    finally:
        if proc:
            osmoutil.end_proc(proc)
        if vty:
           vty._close_socket()

    return ret

def copy_config(dirname, config):
    if os.path.exists(dirname):
        shutil.rmtree(dirname)

    try:
        os.stat(dirname)
    except OSError:
        os.mkdir(dirname)

    prefix = os.path.basename(config)
    tmpfile = tempfile.NamedTemporaryFile(
        dir=dirname, prefix=prefix, delete=False)
    tmpfile.write(open(config).read().encode())
    tmpfile.close()
    # This works around the precautions NamedTemporaryFile is made for...
    return tmpfile.name


def write_config(vty):
    new_config = vty.enabled_command("write")
    if not new_config.startswith("Configuration saved to "):
        print(new_config)
        return 1, [new_config]
    return 0


# The only purpose of this function is to verify a working vty
def token_vty_command(vty):
    vty.command("help")
    return 0


# This may warn about the same doc missing multiple times, by design
def verify_doc(vty):
    xml = vty.command("show online-help")
    split_at = "<command"
    all_errs = []
    for command in xml.split(split_at):
        if "(null)" in command:
            lines = command.split("\n")
            cmd_line = split_at + lines[0]
            err_lines = []
            for line in lines:
                if '(null)' in line:
                    err_lines.append(line)

            all_errs.append(err_lines)

            print("Documentation error (missing docs): \n%s\n%s\n" % (
                cmd_line, '\n'.join(err_lines)), file=sys.stderr)

    return (len(all_errs), all_errs)


# Skip testing the configurations of anything that hasn't been compiled
def app_exists(app_desc):
    cmd = app_desc[1].split(' ')[0]
    return os.path.exists(cmd)


def remove_tmpdir(tmpdir):
    shutil.rmtree(tmpdir)


def check_configs_tested(basedir, app_configs, ignore_configs):
    configs = []
    for root, dirs, files in os.walk(basedir):
        for f in files:
            if f.endswith(".cfg") and f not in ignore_configs:
                configs.append(os.path.join(root, f))
    for config in configs:
        found = False
        for app in app_configs:
            if config in app_configs[app]:
                found = True
        if not found:
            print("Warning: %s is not being tested" % config, file=sys.stderr)


def test_all_apps(apps, app_configs, tmpdir="writtenconfig", verbose=True,
                  confpath=".", ignore_configs=[]):
    check_configs_tested("doc/examples/", app_configs, ignore_configs)
    for app in apps:
        if not app_exists(app):
            print("Skipping app %s (not found)" % app[1], file=sys.stderr)
            continue

        configs = app_configs[app[3]]
        for config in configs:
            config = os.path.join(confpath, config)
            test_config(app, config, tmpdir, verbose)

    remove_tmpdir(tmpdir)


if __name__ == '__main__':
    import argparse

    confpath = "."
    wordir = "."

    parser = argparse.ArgumentParser()
    parser.add_argument("--e1nitb", action="store_true", dest="e1nitb")
    parser.add_argument("-v", "--verbose", dest="verbose",
                        action="store_true", help="verbose mode")
    parser.add_argument("-p", "--pythonconfpath", dest="p",
                        help="searchpath for config")
    parser.add_argument("-w", "--workdir", dest="w",
                        help="Working directory to run in")

    args = parser.parse_args()

    if args.p:
        confpath = args.p

    if args.w:
        workdir = args.w

    osmoappdesc = osmoutil.importappconf_or_quit(confpath, "osmoappdesc",
                                                 args.p)

    apps = osmoappdesc.apps
    configs = osmoappdesc.app_configs
    ignores = getattr(osmoappdesc, 'ignore_configs', [])

    if args.e1nitb:
        configs['nitb'].extend(osmoappdesc.nitb_e1_configs)

    os.chdir(workdir)
    sys.exit(test_all_apps(apps, configs, ignore_configs=ignores,
                           confpath=confpath, verbose=args.verbose))
