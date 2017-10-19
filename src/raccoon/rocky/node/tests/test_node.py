# -*- coding: utf-8 -*-
# :Project:   raccoon.rocky.node -- node tests
# :Created:   gio 24 mar 2016 17:00:52 CET
# :Author:    Alberto Berti <alberto@metapensiero.it>
# :License:   GNU General Public License version 3 or later
# :Copyright: © 2016, 2017 Arstecnica s.r.l.
#

# from unittest.mock import patch

import asyncio
import pytest

from metapensiero.signal import Signal, handler

from raccoon.rocky.node.path import Path
from raccoon.rocky.node.node import Node
from raccoon.rocky.node.wamp import call, WAMPNode


@pytest.mark.asyncio
async def test_node_basic(node_context, event_loop):

    node = Node()

    assert node.loop is None
    assert node.node_root is node
    assert node.node_path is None
    assert node.node_context is None

    assert node_context.loop is event_loop

    path = Path('raccoon.test')

    # with patch.object(node, 'on_node_bind') as bind_event:
    #     await node.node_bind(path, node_context)
    #     bind_event.notify.assert_called_with(node=node, path=path, parent=None,
    #                                          run_async=True)

    await node.node_bind(path, node_context)
    assert node.loop is node_context.loop
    assert node.node_root is node
    assert node.node_path is path
    assert node.node_context._parent_context is node_context

    # with patch.object(node, 'on_node_unbind') as unbind_event:
    #     await node.node_unbind()
    #     unbind_event.notify.assert_called_with(node=node, path=path, parent=None)

    await node.node_unbind()
    assert node.loop is None
    assert node.node_root is node
    assert node.node_path is None
    assert node.node_context is None


@pytest.mark.asyncio
async def test_node_add(node_context):

    n1 = Node()
    n2 = Node()

    path = Path('raccoon.test')

    await n1.node_bind(path, node_context)

    # with patch.object(n1, 'on_node_add') as add_event:
    #     await n1.node_add('foo', n2)
    #     add_event.notify.assert_called_with(path=Path('raccoon.test.foo'),
    #                                         node=n2)

    await n1.node_add('foo', n2)
    assert n2.loop is node_context.loop
    assert n2.node_root is n1
    assert n2.node_path is Path('raccoon.test.foo')
    assert n2.node_context._parent_context is n1.node_context

    await n1.node_remove('foo')

    assert n2.loop is None
    assert n2.node_root is n2
    assert n2.node_path is None
    assert n2.node_context is None


@pytest.mark.asyncio
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


@pytest.mark.asyncio
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


@pytest.mark.asyncio
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


@pytest.mark.asyncio
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


@pytest.mark.asyncio
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

@pytest.mark.asyncio
async def test_node_unbind(node_context):

    nodes = []
    parent = Node()
    await parent.node_bind('root', node_context)
    nodes.append(parent)

    counter = 0
    def on_unbind(**_):
        nonlocal counter
        counter += 1

    for i in range(2, 5):
        p = nodes[-1]
        for y in range(i):
            n = Node()
            n.on_node_unbind.connect(on_unbind)
            name = 'n' + str(i) + str(y)
            await p.node_add(name, n)
            nodes.append(n)

    assert hasattr(parent, 'n20')

    await parent.node_unbind()
    assert counter == 2 + 3 + 4
    assert not hasattr(parent, 'n20')


@pytest.mark.asyncio
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


@pytest.mark.asyncio
async def test_node_unbind_runs_only_one_time():

    class MyNode(Node):

        _counts = 0

        async def _node_unbind(self):
            self._counts += 1


    my_node = MyNode()

    async def unbind_it(node):
        await node.node_unbind()

    unbind1 = asyncio.ensure_future(unbind_it(my_node))
    unbind2 = asyncio.ensure_future(unbind_it(my_node))

    await unbind1
    await unbind2

    assert my_node._counts == 1
