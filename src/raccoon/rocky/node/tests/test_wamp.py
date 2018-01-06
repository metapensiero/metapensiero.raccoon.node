# -*- coding: utf-8 -*-
# :Project:   metapensiero.raccoon.node -- wamp stuff tests
# :Created:   mar 22 mar 2016 19:12:45 CET
# :Author:    Alberto Berti <alberto@metapensiero.it>
# :License:   GNU General Public License version 3 or later
# :Copyright: © 2016, 2017, 2018 Alberto Berti
#

import pytest

from unittest.mock import patch

from metapensiero.signal import Signal, handler
from raccoon.rocky.node.context import WAMPNodeContext
from raccoon.rocky.node.path import Path
from raccoon.rocky.node.wamp import (call, WAMPInitMeta, AbstractWAMPNode,
                                     node_wamp_manager)


class FakeNode(metaclass=WAMPInitMeta):
    """A fake Node class that emulates the interesting API of
    r.r.node.node.WAMPNode, just to test the wamp stuff"""

    on_node_register = Signal()
    on_node_registration_success = Signal()
    on_node_registration_failure = Signal()
    on_node_unregister = Signal()

    node_registered = False

    def __init__(self, context, path):
        self.node_context = context
        self.node_path = path
        self.loop = context.loop

    async def node_register(self):
        self.node_registered = True
        await self.on_node_register.notify(node=self,
                                           context=self.node_context)

    async def node_unregister(self):
        self.node_registered = False
        await self.on_node_unregister.notify(node=self,
                                             context=self.node_context)

AbstractWAMPNode.register(FakeNode)


@pytest.mark.asyncio
async def test_register_and_call_rpc(wamp_context, event_loop):

    reg_success = False

    class RPCTest(FakeNode):

        @handler('on_node_registration_success')
        def reg_success(*args, **kwargs):
            nonlocal reg_success
            reg_success = True

        @call
        def callme(self, *args, **kwargs):
            pass

    path = Path('raccoon.test')
    rpc_test = RPCTest(wamp_context, path)

    with patch.object(rpc_test, 'callme') as callme:
        await rpc_test.node_register()
        wsess = wamp_context.wamp_session
        callme.return_value = None


        # This cannot be checked anymore because the handler is now a partial.
        # wsess.register.assert_called_with(
        #     node_wamp_manager._dispatch_procedure,
        #     'raccoon.test.callme',
        #     options=wsess.last_register_opts.return_value
        # )
        assert reg_success
        await wsess.call(str(path.callme), 1, 'a', kw='foo')
        callme.assert_called_with(1, 'a', kw='foo',
                                  details=wsess.last_calldetails.return_value)


@pytest.mark.asyncio
async def test_subscriber_and_publisher(wamp_context, wamp_context2, event_loop):

    class RPCTest(FakeNode):

        on_test_event = Signal()


    class RPCTest2(FakeNode):

        @handler('@test.on_test_event')
        def test_handler(self, *args, **kwargs):
            pass

    base = Path('raccoon')
    path = Path('test', base)
    path2 = Path('test2', base)
    rpc_test = RPCTest(wamp_context, path)
    rpc_test2 = RPCTest2(wamp_context2, path2)

    with patch.object(rpc_test2, 'test_handler') as thandler:
        await rpc_test.node_register()
        await rpc_test2.node_register()
        wsess = wamp_context2.wamp_session

        # This cannot be checked anymore because the handler is now a partial.
        # wsess.subscribe.assert_called_with(
        #     node_wamp_manager._dispatch_event,
        #     'raccoon.test.on_test_event',
        #     options=wsess.last_subscribe_opts.return_value
        # )
        await rpc_test.on_test_event.notify(1, 'a', kw='foo')
        thandler.assert_called_with(1, 'a', kw='foo',
            details=wsess.last_publish_details.return_value)
