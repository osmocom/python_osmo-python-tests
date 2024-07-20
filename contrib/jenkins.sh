#!/bin/sh

set -ex

PY3=python3

rm -rf ./env
virtualenv --system-site-packages env
. ./env/bin/activate
pip install .

# Run async server which tests scripts/osmo_ctrl.py interaction
$PY3 tests/test_py3.py

# TODO: add more tests
