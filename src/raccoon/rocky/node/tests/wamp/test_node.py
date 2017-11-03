# -*- coding: utf-8 -*-
# :Project:   raccoon.rocky.node -- wamp node tests
# :Created:   gio 26 ott 2017 01:07:10 CEST
# :Author:    Alberto Berti <alberto@metapensiero.it>
# :License:   GNU General Public License version 3 or later
# :Copyright: © 2017 Arstecnica s.r.l.
#

import asyncio
import pytest

from metapensiero.signal import Signal, handler

from raccoon.rocky.node.path import Path
from raccoon.rocky.node.wamp import call, WAMPNode

# All test coroutines will be treated as marked
pytestmark = pytest.mark.asyncio()


async def test_call_method(wamp_context, event_loop):

    class RPCTest(WAMPNode):

        @call
        def foo(self, *args, **_):
            from functools import reduce
            return reduce(lambda n, acc: n + acc, args)

    class RPCTest2(WAMPNode):

        async def bar(self):
            return await self.call('@test.foo', 1, 2, 3)

    base = Path('raccoon')
    path = Path('test', base)
    path2 = Path('test2', base)
    rpc_test = RPCTest()
    await rpc_test.node_bind(path, wamp_context)
    rpc_test2 = RPCTest2()
    await rpc_test2.node_bind(path2, wamp_context)

    res = await rpc_test2.bar()
    assert res == 6


async def test_proxy_call(wamp_context, event_loop):

    class RPCTest(WAMPNode):

        @call
        def foo(self, *args, **_):
            from functools import reduce
            return reduce(lambda n, acc: n + acc, args)

    class RPCTest2(WAMPNode):

        async def bar(self):
            return await self.remote('@test').foo(1, 2, 3)

    base = Path('raccoon')
    path = Path('test', base)
    path2 = Path('test2', base)
    rpc_test = RPCTest()
    await rpc_test.node_bind(path, wamp_context)
    rpc_test2 = RPCTest2()
    await rpc_test2.node_bind(path2, wamp_context)

    res = await rpc_test2.bar()
    assert res == 6


async def test_node_unregister(wamp_context, event_loop):

    class RPCTest(WAMPNode):
        pass

    class MySubNode(WAMPNode):

        @call
        def foo(self, *args, **_):
            from functools import reduce
            return reduce(lambda n, acc: n + acc, args)

    class RPCTest2(WAMPNode):

        async def bar(self):
            return await self.remote('@test').sub.foo(1, 2, 3)

    base = Path('raccoon')
    path = Path('test', base)
    path2 = Path('test2', base)
    rpc_test = RPCTest()
    await rpc_test.node_bind(path, wamp_context)
    await rpc_test.node_add('sub', MySubNode())
    rpc_test2 = RPCTest2()
    await rpc_test2.node_bind(path2, wamp_context)

    res = await rpc_test2.bar()
    assert res == 6
    await rpc_test.node_remove('sub')

    with pytest.raises(Exception):
        res = await rpc_test2.bar()


async def test_proxy_handler(wamp_context, event_loop, events):

    counter = 0
    events.define('bar', 'tmp')

    class RPCTest(WAMPNode):

        foo = Signal()

        @handler('foo')
        def local_bar(self, **_):
            nonlocal counter
            counter += 1

    class RPCTest2(WAMPNode):

        @handler('@test.foo')
        def bar(self, **_):
            nonlocal counter
            counter += 1
            events.bar.set()

        def other_handler(self, **_):
            nonlocal counter
            counter += 1
            events.tmp.set()

        def add_second_handler(self):
            return self.remote('@test').foo.connect(self.other_handler)

        def remove_second_handler(self):
            return self.remote('@test').foo.disconnect(self.other_handler)

    base = Path('raccoon')
    path = Path('test', base)
    path2 = Path('test2', base)
    rpc_test = RPCTest()
    rpc_test.name = 'rpc_test'
    await rpc_test.node_bind(path, wamp_context)
    rpc_test2 = RPCTest2()
    await rpc_test2.node_bind(path2, wamp_context)

    await rpc_test.foo.notify(awaitable=True)

    await events.wait_for(events.bar, 5)
    assert counter == 2
    events.reset()
    counter = 0
    rpc_test2.remote('@test').foo.notify(awaitable=True)
    await events.wait_for(events.bar, 5)
    assert counter == 2
    events.reset()
    counter = 0
    await rpc_test2.add_second_handler()

    await rpc_test.foo.notify(awaitable=True)

    await events.wait(timeout=5)
    assert counter == 3
    events.reset()
    counter = 0
    await rpc_test2.remove_second_handler()

    await rpc_test.foo.notify(awaitable=True)

    await events.wait(timeout=2)
    assert counter == 2


async def test_proxy_handler_two_sessions(wamp_context,  wamp_context2,
                                          event_loop, events):

    counter = 0
    events.define('bar', 'tmp')

    class RPCTest(WAMPNode):

        foo = Signal()

        @handler('foo')
        def local_bar(self, **_):
            nonlocal counter
            counter += 1

    class RPCTest2(WAMPNode):

        @handler('@test.foo')
        def bar(self, **_):
            nonlocal counter
            counter += 1
            events.bar.set()

        def other_handler(self, **_):
            nonlocal counter
            counter += 1
            events.tmp.set()

        def add_second_handler(self):
            return self.remote('@test').foo.connect(self.other_handler)

        def remove_second_handler(self):
            return self.remote('@test').foo.disconnect(self.other_handler)

    base = Path('raccoon')
    path = Path('test', base)
    path2 = Path('test2', base)
    rpc_test = RPCTest()
    rpc_test.name = 'rpc_test'
    await rpc_test.node_bind(path, wamp_context)
    rpc_test2 = RPCTest2()
    await rpc_test2.node_bind(path2, wamp_context2)

    await rpc_test.foo.notify(awaitable=True)

    await events.wait_for(events.bar, 5)
    assert counter == 2
    events.reset()
    counter = 0
    rpc_test2.remote('@test').foo.notify()
    await events.wait_for(events.bar, 5)
    assert counter == 2
    events.reset()
    counter = 0
    await rpc_test2.add_second_handler()

    await rpc_test.foo.notify(awaitable=True)

    await events.wait(timeout=5)
    assert counter == 3

    events.reset()
    counter = 0
    await rpc_test2.remove_second_handler()

    await rpc_test.foo.notify(awaitable=True)

    await events.wait(timeout=2)
    assert counter == 2


async def test_call_dot(wamp_context,  wamp_context2,
                        event_loop, events):

    counter = 0
    events.define('me_handler')

    class RPCTest(WAMPNode):

        foo = Signal()
        foo.name = '.'

        @call('.')
        def me(self, **_):
            nonlocal counter
            counter += 1
            return counter

    class RPCTest2(WAMPNode):

        @handler('test')
        def on_test_dot(self, *_, **__):
            events.me_handler.set()

    base = Path('raccoon')
    path = Path('test', base)
    path2 = Path('test2', base)
    rpc_test = RPCTest()
    rpc_test.name = 'rpc_test'
    await rpc_test.node_bind(path, wamp_context)
    rpc_test2 = RPCTest2()
    await rpc_test2.node_bind(path2, wamp_context2)

    res = await rpc_test2.call('@test')
    assert res == counter == 1
    await rpc_test.foo.notify(awaitable=True)
    assert events.me_handler.is_set()
    events.me_handler.clear()
    await rpc_test2.remote('@test').notify(awaitable=True)
    assert events.me_handler.is_set()
