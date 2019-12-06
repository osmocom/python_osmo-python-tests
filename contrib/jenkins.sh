#!/bin/sh

set -ex

COM_FLAGS='-m compileall'

# FIXME: remove once python 2 support is deprecated
PY2=python2
PY2_LIST="osmopy scripts/osmodumpdoc.py scripts/osmotestvty.py scripts/osmotestconfig.py"
$PY2 ./setup.py install
$PY2 tests/test_py2.py
for f in $PY2_LIST
do
    $PY2 $COM_FLAGS $f
done

rm -rf ./build
PY3=python3
PY3_LIST="osmopy scripts/osmo_ctrl.py scripts/osmo_rate_ctr2csv.py scripts/osmodumpdoc.py scripts/osmotestvty.py scripts/osmotestconfig.py scripts/osmo_interact_ctrl.py scripts/osmo_interact_vty.py scripts/osmo_verify_transcript_ctrl.py scripts/osmo_verify_transcript_vty.py scripts/soap.py scripts/twisted_ipa.py"
$PY3 ./setup.py install
$PY3 tests/test_py3.py
for f in $PY3_LIST
do
    $PY3 $COM_FLAGS $f
done

# Run async server which tests scripts/osmo_ctrl.py interaction
$PY3 tests/test_py3.py

# TODO: add more tests
