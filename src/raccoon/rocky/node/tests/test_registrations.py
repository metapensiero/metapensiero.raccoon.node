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

    def bar(self):
        pass


@pytest.mark.asyncio
async def test_registry():
    reg = Registry()

    fn = FakeNode()
    point = HandlerKey(fn, fn.foo).point()
    async with reg.new_session_for(fn) as session:
        session.add_point(point, 'test.foo')
    p = Path('test.foo')

    assert p in reg
    record = reg[p]
    assert point in record.points.values()

    async with reg.new_session_for(fn) as session:
        session.remove_point(point)
    assert p not in reg


@pytest.mark.asyncio
async def test_registry_events():
    reg = Registry()

    sessions = []
    def _collect_session(session):
        sessions.append(session)

    reg.on_session_complete.connect(_collect_session)

    fn = FakeNode()
    point = HandlerKey(fn, fn.foo).point()
    async with reg.new_session_for(fn) as session:
        session.add_point(point, 'test.foo')
    p = Path('test.foo')

    assert len(sessions) == 1
    assert sessions[-1].added == ((p, point.rpc_type),)
    assert sessions[-1].removed == ()

    point2 = HandlerKey(fn, fn.bar).point()
    async with reg.new_session_for(fn) as session:
        session.add_point(point2, 'test.foo')

    assert len(sessions) == 2
    assert sessions[-1].added == ()
    assert sessions[-1].removed == ()

    async with reg.new_session_for(fn) as session:
        session.remove_point(point)

    assert len(sessions) == 3
    assert sessions[-1].added == ()
    assert sessions[-1].removed == ()


    async with reg.new_session_for(fn) as session:
        session.remove_point(point2)

    assert len(sessions) == 4
    assert sessions[-1].added == ()
    assert sessions[-1].removed == ((p, point.rpc_type),)


def test_record():
    fn = FakeNode()
    point = HandlerKey(fn, fn.foo).point()
    p = Path('test.foo')
    record = RPCRecord(p)
    point.attach(record)
    assert point in record[fn]
    assert point in record[RPCType.EVENT]
    assert point is record[HandlerKey(fn, fn.foo)]
