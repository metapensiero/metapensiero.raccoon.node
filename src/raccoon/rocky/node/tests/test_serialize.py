# -*- coding: utf-8 -*-
# :Project:   raccoon.rocky.node -- node tests
# :Created:   mar 06 giu 2017 19:39:00 CEST
# :Author:    Alberto Berti <alberto@metapensiero.it>
# :License:   GNU General Public License version 3 or later
# :Copyright: © 2017 Arstecnica s.r.l.
#

import pytest

from metapensiero.signal import handler, Signal
from raccoon.rocky.node import Path, serialize
from raccoon.rocky.node.wamp import call, Proxy, WAMPNode


@serialize.define('test.Simple', allow_subclasses=True)
class SimpleSerializable(serialize.Serializable):

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs

    def __eq__(self, other):
        return self.args == other.args and self.kwargs == other.kwargs

    @classmethod
    def node_deserialize(cls, value, end_node):
        return cls(*value[0], **value[1])

    @classmethod
    def node_serialize(cls, instance, src_node):
        return serialize.Serialized((instance.args, instance.kwargs))


class SimpleSub(SimpleSerializable):
    pass


class NonSerializable:
    pass


class ExtSerializer(serialize.Serializable):

    @classmethod
    def node_deserialize(cls, value, end_node):
        return SerializableExt(*value[0], **value[1])

    @classmethod
    def node_serialize(cls, instance, src_node):
        return instance.args, instance.kwargs


@serialize.define('test.SimpleExt', serializer=ExtSerializer())
class SerializableExt:

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs

    def __eq__(self, other):
        return self.args == other.args and self.kwargs == other.kwargs


def test_serialize_fails():

    with pytest.raises(serialize.SerializationError) as exc_info:
        serialize.serialize(NonSerializable())

    exc_info.match("Don't know how")

    with pytest.raises(serialize.SerializationError) as exc_info:
        serialize.deserialize({})

    exc_info.match("is not a valid serialized")

    with pytest.raises(serialize.SerializationError) as exc_info:
        serialize.deserialize(serialize.Serialized(None, 'not.really.a.serial'))

    exc_info.match("Don't know how")


def test_serialize_simple():

    inst = SimpleSerializable(1, b=2)
    value = serialize.serialize(inst)
    assert isinstance(value, serialize.Serialized)
    sid = serialize.Serialized.get_id(value)
    assert sid == 'test.Simple'
    svalue = serialize.Serialized.get_value(value)
    assert svalue == ((1,), {'b': 2})

    inst2 = serialize.deserialize(value)
    assert isinstance(inst2, SimpleSerializable)
    assert inst2 is not inst
    assert inst2 == inst


def test_serialize_simplesub():

    inst = SimpleSub(1, b=2)
    value = serialize.serialize(inst)
    assert isinstance(value, serialize.Serialized)
    sid = serialize.Serialized.get_id(value)
    assert sid == 'test.Simple'
    svalue = serialize.Serialized.get_value(value)
    assert svalue == ((1,), {'b': 2})

    inst2 = serialize.deserialize(value)
    assert isinstance(inst2, SimpleSerializable)
    assert not isinstance(inst2, SimpleSub)
    assert inst2 is not inst
    assert inst2 == inst


def test_serialize_ext():

    assert issubclass(SerializableExt, serialize.Serializable)
    inst = SerializableExt(1, b=2)
    value = serialize.serialize(inst)
    assert isinstance(value, serialize.Serialized)
    sid = serialize.Serialized.get_id(value)
    assert sid == 'test.SimpleExt'
    svalue = serialize.Serialized.get_value(value)
    assert svalue == ((1,), {'b': 2})

    inst2 = serialize.deserialize(value)
    assert isinstance(inst2, SerializableExt)
    assert inst2 is not inst
    assert inst2 == inst


@pytest.mark.asyncio
async def test_serialize_node_same_session_no_serialization(
        wamp_context, event_loop, events):

    events.define('asignal')

    class RPCTest(WAMPNode):

        asignal = Signal()

        @call
        def callee(self):
            return self

        @handler('asignal')
        def store_incoming(self, node):
            events.asignal.set()
            self.node = node

    class RPCTest2(WAMPNode):

        async def caller(self):
            return await self.call('@test.callee')

    base = Path('raccoon')
    path = Path('test', base)
    path2 = Path('test2', base)
    rpc_test = RPCTest()
    await rpc_test.node_bind(path, wamp_context)
    rpc_test2 = RPCTest2()
    await rpc_test2.node_bind(path2, wamp_context)

    res = await rpc_test2.caller()
    assert res is rpc_test

    rpc_test2.remote('@test').asignal.notify(rpc_test2)
    await events.wait_for(events.asignal, 5)
    assert rpc_test.node is rpc_test2


@pytest.mark.asyncio
async def test_serialize_node_two_sessions_do_serialize(
        wamp_context,  wamp_context2, event_loop, events):

    events.define('asignal')

    class RPCTest(WAMPNode):

        asignal = Signal()

        @call
        def callee(self):
            return self

        @handler('asignal')
        def store_incoming(self, node):
            events.asignal.set()
            self.node = node

    class RPCTest2(WAMPNode):

        async def caller(self):
            return await self.call('@test.callee')

    base = Path('raccoon')
    path = Path('test', base)
    path2 = Path('test2', base)
    rpc_test = RPCTest()
    rpc_test.name = 'rpc_test'
    await rpc_test.node_bind(path, wamp_context)
    rpc_test2 = RPCTest2()
    await rpc_test2.node_bind(path2, wamp_context2)

    res = await rpc_test2.caller()
    assert res is not rpc_test
    assert isinstance(res, Proxy)
    assert res.node_path == path

    rpc_test2.remote('@test').asignal.notify(rpc_test2)
    await events.wait_for(events.asignal, 5)
    assert rpc_test.node is not rpc_test2
    assert isinstance(rpc_test.node, Proxy)
    assert rpc_test.node.node_path == path2
