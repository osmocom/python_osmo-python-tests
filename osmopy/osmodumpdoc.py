#!/usr/bin/env python

# Make sure this code is in sync with the BTS directory.
# Fixes may need to be applied to both.

"""Start the process and dump the documentation to the doc dir."""

import subprocess
import time
import os
import sys

import osmopy.obscvty as obscvty
import osmopy.osmoutil as osmoutil


def dump_doc(name, port, filename):
    vty = obscvty.VTYInteract(name, "127.0.0.1", port)
    xml = vty.command("show online-help")
    # Now write everything until the end to the file
    out = open(filename, 'w')
    out.write(xml)
    out.close()


"""Dump the config of all the apps.

Returns the number of apps configs could not be dumped for."""


def dump_configs(apps, configs):
    failures = 0
    successes = 0

    try:  # make sure the doc directory exists
        os.mkdir('doc')
    except OSError:  # it probably does
        pass

    for app in apps:
        appname = app[3]
        print "Starting app for %s" % appname
        proc = None
        cmd = [app[1], "-c", configs[appname][0]]
        try:
            proc = subprocess.Popen(cmd, stdin=None, stdout=None)
        except OSError:  # Probably a missing binary
            print >> sys.stderr, "Skipping app %s" % appname
            failures += 1
        else:
            time.sleep(1)
            try:
                dump_doc(app[2], app[0], 'doc/%s_vty_reference.xml' % appname)
                successes += 1
            except IOError:  # Generally a socket issue
                print >> sys.stderr, "%s: couldn't connect, skipping" % appname
                failures += 1
        finally:
            osmoutil.end_proc(proc)

    return (failures, successes)


if __name__ == '__main__':
    import argparse

    confpath = "."
    workdir = "."

    parser = argparse.ArgumentParser()
    parser.add_argument("-p", "--pythonconfpath", dest="p",
                        help="searchpath for config (osmoappdesc)")
    parser.add_argument("-w", "--workdir", dest="w",
                        help="Working directory to run in")
    args = parser.parse_args()

    if args.p:
        confpath = args.p

    if args.w:
        workdir = args.w

    osmoappdesc = None
    try:
        osmoappdesc = osmoutil.importappconf(confpath, "osmoappdesc")
    except ImportError as e:
        print >> sys.stderr, "osmoappdesc not found, set searchpath with -p"
        sys.exit(1)

    os.chdir(workdir)
    num_fails, num_sucs = dump_configs(
        osmoappdesc.apps, osmoappdesc.app_configs)
    if num_fails > 0:
        print >> sys.stderr, "Warning: Skipped %s apps" % num_fails
        if 0 == num_sucs:
            print >> sys.stderr, "Nothing run, wrong working dir? Set with -w"
    sys.exit(num_fails)
