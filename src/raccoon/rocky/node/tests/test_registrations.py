# -*- coding: utf-8 -*-
# :Project:   raccoon.rocky.node -- node tests
# :Created:   lun 12 dic 2016 11:13:43 CET
# :Author:    Alberto Berti <alberto@metapensiero.it>
# :License:   GNU General Public License version 3 or later
# :Copyright: Copyright (C) 2016 Arstecnica s.r.l.
#

import pytest

from raccoon.rocky.node.registry import EndPoint


# class FakeContext:

#     wamp_session = object()


# class FakeNode:

#     node_context = FakeContext()

#     def foo(self):
#         pass

# def test_endpointdefs():

#     node = FakeNode()
#     epd = RPCPoint(node, node.foo)
#     store = set([epd])

#     assert epd in store

#     epd2 = RPCPoint(node, node.foo)

#     assert epd2 in store
