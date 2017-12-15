#!/bin/sh
python2 ./setup.py install || python ./setup.py install
rm -rf ./build
python3 ./setup.py install
