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

# All test coroutines will be treated as marked
pytestmark = pytest.mark.asyncio()


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
