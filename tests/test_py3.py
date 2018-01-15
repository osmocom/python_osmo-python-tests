#!/usr/bin/env python3

# just a smoke test for osmopy

import asyncio, random, sys, os

# we have to use this ugly hack to workaroundbrokenrelative imports in py3:
# from ..osmopy.osmo_ipa import Ctrl
# does not work as expected
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
from osmopy.osmo_ipa import Ctrl
from osmopy import __version__

class CtrlProtocol(asyncio.Protocol):
    def connection_made(self, transport):
        peername = transport.get_extra_info('peername')
        print('Connection from {}'.format(peername))
        self.transport = transport

    def data_received(self, data):
        (i, v, k) = Ctrl().parse(data)
        if not k:
            print('Ctrl GET received: %s' % v)
        else:
            print('Ctrl SET received: %s :: %s' % (v, k))

        message = Ctrl().reply(i, v, k)
        self.transport.write(message)

        self.transport.close()
        # quit the loop gracefully
        print('Closing the loop...')
        loop.stop()


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    test_host = '127.0.0.5'
    test_port = str(random.randint(1025, 60000))

    print('Testing v%s on %s:%s' % (__version__, test_host, test_port))

    # Each client connection will create a new protocol instance
    server = loop.run_until_complete(loop.create_server(CtrlProtocol, test_host, test_port))

    print('Serving on {}...'.format(server.sockets[0].getsockname()))

    # Async client running in the subprocess plugged to the same event loop
    loop.run_until_complete(asyncio.gather(asyncio.create_subprocess_exec('./scripts/osmo_ctrl.py', '-g', 'mnc', '-d', test_host, '-p', test_port), loop = loop))

    loop.run_forever()

    # Cleanup after loop is finished
    server.close()
    loop.run_until_complete(server.wait_closed())
    loop.close()

    print('[Python3] Smoke test PASSED for v%s' % __version__)
