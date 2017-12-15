#!/bin/sh

set -ex

# FIXME: remove once python 2 support is deprecated
python2 ./setup.py install
python2 tests/test_py2.py

rm -rf ./build
python3 ./setup.py install
python3 tests/test_py3.py

# TODO: add more tests
