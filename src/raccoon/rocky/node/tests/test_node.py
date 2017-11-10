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
from unittest.mock import patch

from metapensiero.signal import Signal, handler

from raccoon.rocky.node import call, Node, Path
from raccoon.rocky.node.errors import DispatchError

# All test coroutines will be treated as marked
pytestmark = pytest.mark.asyncio()


async def _mock_future(result=None):
    f = asyncio.get_event_loop().create_future()
    f.set_result(result)
    return f


async def test_node_basic(node_context, event_loop):

    node = Node()

    assert node.loop is None
    assert node.node_root is node
    assert node.node_path is None
    assert node.node_context is None

    assert node_context.loop is event_loop

    path = Path('raccoon.test')

    with patch.object(node, 'on_node_bind') as bind_event:
        bind_event.notify.return_value = await _mock_future()
        await node.node_bind(path, node_context)
        bind_event.notify.assert_called_with(node=node, path=path, parent=None)

    assert node.loop is node_context.loop
    assert node.node_root is node
    assert node.node_path is path
    assert node.node_context._parent_context is node_context

    with patch.object(node, 'on_node_unbind') as unbind_event:
        unbind_event.notify.return_value = await _mock_future()
        await node.node_unbind()
        unbind_event.notify.assert_called_with(node=node, path=path,
                                               parent=None)

    assert node.loop is None
    assert node.node_root is node
    assert node.node_path is None
    assert node.node_context is None


async def test_node_add(node_context):

    n1 = Node()
    n2 = Node()

    path = Path('raccoon.test')

    await n1.node_bind(path, node_context)

    with patch.object(n1, 'on_node_add') as add_event:
        add_event.notify.return_value = await _mock_future()
        await n1.node_add('foo', n2)
        add_event.notify.assert_called_with(path=Path('raccoon.test.foo'),
                                            node=n2)

    assert n2.loop is node_context.loop
    assert n2.node_root is n1
    assert n2.node_path is Path('raccoon.test.foo')
    assert n2.node_context._parent_context is n1.node_context

    await n1.node_remove('foo')

    assert n2.loop is None
    assert n2.node_root is n2
    assert n2.node_path is None
    assert n2.node_context is None


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


async def test_node_unbind_runs_only_one_time(node_context):

    class MyNode(Node):

        _counts = 0

        async def _node_unbind(self):
            self._counts += 1

    my_node = MyNode()

    await my_node.node_bind('test.it', node_context)

    async def unbind_it(node):
        await node.node_unbind()

    unbind1 = asyncio.ensure_future(unbind_it(my_node))
    unbind2 = asyncio.ensure_future(unbind_it(my_node))

    await unbind1
    await unbind2

    assert my_node._counts == 1


async def test_call_method(node_context, event_loop):

    class RPCTest(Node):

        @call
        def foo(self, *args):
            from functools import reduce
            return reduce(lambda n, acc: n + acc, args)

    class RPCTest2(Node):

        async def bar(self):
            return await self.node_call('@test.foo', 1, 2, 3)

    base = Path('raccoon')
    path = Path('test', base)
    path2 = Path('test2', base)
    rpc_test = RPCTest()
    await rpc_test.node_bind(path, node_context)
    rpc_test2 = RPCTest2()
    await rpc_test2.node_bind(path2, node_context)

    res = await rpc_test2.bar()
    assert res == 6


async def test_node_unregister(node_context, event_loop):

    class RPCTest(Node):
        pass

    class MySubNode(Node):

        @call
        def foo(self, *args):
            from functools import reduce
            return reduce(lambda n, acc: n + acc, args)

    class RPCTest2(Node):

        async def bar(self):
            return await self.node_call('@test.sub.foo',1, 2, 3)

    base = Path('raccoon')
    path = Path('test', base)
    path2 = Path('test2', base)
    rpc_test = RPCTest()
    await rpc_test.node_bind(path, node_context)
    await rpc_test.node_add('sub', MySubNode())
    rpc_test2 = RPCTest2()
    await rpc_test2.node_bind(path2, node_context)

    res = await rpc_test2.bar()
    assert res == 6
    await rpc_test.node_remove('sub')

    with pytest.raises(DispatchError):
        res = await rpc_test2.bar()


async def test_runtime_handler(node_context, event_loop, events):

    counter = 0
    events.define('bar', 'tmp')

    class RPCTest(Node):

        foo = Signal()

        @handler('foo')
        def local_bar(self):
            nonlocal counter
            counter += 1

    class RPCTest2(Node):

        @handler('@test.foo')
        def bar(self):
            nonlocal counter
            counter += 1
            events.bar.set()

        def other_handler(self):
            nonlocal counter
            counter += 1
            events.tmp.set()

        def add_second_handler(self):
            return self.node_connect('@test.foo', self.other_handler)

        def remove_second_handler(self):
            return self.node_disconnect('@test.foo', self.other_handler)

    base = Path('raccoon')
    path = Path('test', base)
    path2 = Path('test2', base)
    rpc_test = RPCTest()
    rpc_test.name = 'rpc_test'
    await rpc_test.node_bind(path, node_context)
    rpc_test2 = RPCTest2()
    await rpc_test2.node_bind(path2, node_context)

    await rpc_test.foo.notify()

    await events.wait_for(events.bar, 5)
    assert counter == 2
    events.reset()
    counter = 0
    rpc_test2.node_notify('@test.foo')
    await events.wait_for(events.bar, 5)
    assert counter == 2
    events.reset()
    counter = 0
    await rpc_test2.add_second_handler()

    await rpc_test.foo.notify()

    await events.wait(timeout=5)
    assert counter == 3
    events.reset()
    counter = 0
    await rpc_test2.remove_second_handler()

    await rpc_test.foo.notify()

    await events.wait(events.tmp, timeout=5)
    assert counter == 2


async def test_call_dot(node_context, event_loop, events):

    counter = 0
    events.define('me_handler')

    class RPCTest(Node):

        foo = Signal()
        foo.name = '.'

        @call('.')
        def me(self):
            nonlocal counter
            counter += 1
            return counter

    class RPCTest2(Node):

        @handler('@test')
        def on_test_dot(self):
            events.me_handler.set()

    base = Path('raccoon')
    path = Path('test', base)
    path2 = Path('test2', base)
    rpc_test = RPCTest()
    rpc_test.name = 'rpc_test'
    await rpc_test.node_bind(path, node_context)
    rpc_test2 = RPCTest2()
    await rpc_test2.node_bind(path2, node_context)

    res = await rpc_test2.node_call('@test')
    assert res == counter == 1
    await rpc_test.foo.notify()
    assert events.me_handler.is_set()
    events.me_handler.clear()
    await rpc_test2.node_notify('@test')
    assert events.me_handler.is_set()
