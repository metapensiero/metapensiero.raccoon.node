# -*- coding: utf-8 -*-
# :Project:   raccoon.rocky.node -- node tests
# :Created:   lun 12 dic 2016 11:13:43 CET
# :Author:    Alberto Berti <alberto@metapensiero.it>
# :License:   GNU General Public License version 3 or later
# :Copyright: Copyright (C) 2016 Arstecnica s.r.l.
#

import pytest

from raccoon.rocky.node import Path
from raccoon.rocky.node.registry import (EndPoint, HandlerKey, Registry,
                                         RPCRecord, RPCType)


class FakeNode:

    def foo(self):
        pass



@pytest.mark.asyncio
async def test_registry():
    reg = Registry()

    fn = FakeNode()
    point = HandlerKey(fn, fn.foo).point()
    await reg.add_point(point, 'test.foo')
    p = Path('test.foo')

    assert p in reg
    record = reg[p]
    assert point in record.points.values()

    await reg.remove_point(point)
    assert p not in reg


def test_record():
    fn = FakeNode()
    point = HandlerKey(fn, fn.foo).point()
    p = Path('test.foo')
    record = RPCRecord(p)
    point.attach(record)
    assert point in record[fn]
    assert point in record[RPCType.EVENT]
    assert point is record[HandlerKey(fn, fn.foo)]
