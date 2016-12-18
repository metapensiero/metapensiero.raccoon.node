# -*- coding: utf-8 -*-
# :Project:   raccoon.rocky.node -- registration management
# :Created:   mar 16 feb 2016 16:17:35 CET
# :Author:    Alberto Berti <alberto@metapensiero.it>
# :License:   GNU General Public License version 3 or later
# :Copyright: Copyright (C) 2016 Arstecnica s.r.l.
#

import asyncio
from functools import partial
from weakref import WeakKeyDictionary, WeakValueDictionary

from autobahn.wamp.request import Subscription, Registration
from autobahn.wamp.types import (SubscribeOptions, RegisterOptions)
from metapensiero.asyncio import transaction


class RPCPointMeta(type):

    all = WeakValueDictionary()

    def __call__(cls, node, func=None, store_item=None, *, is_source=False):
        key = hash(frozenset((node, func)))
        if key in cls.all:
            res = cls.all[key]
        else:
            res = super().__call__(node, func=func, store_item=store_item,
                                   is_source=False)
            cls.all[hash(res)] = res
        return res


class RPCPoint(metaclass=RPCPointMeta):

    def __init__(self, node, func=None, store_item=None, *, is_source=False):
        self.store_item = store_item
        self.node = node
        self.func = func
        self.is_source = is_source
        self._key = frozenset([node, func])
        self.session = node.node_context.wamp_session

    def __hash__(self):
        return hash(self._key)

    def __repr__(self):
        return "<{} for node '{}' and func '{}'>".format(
            self.__class__.__name__, self.node, self.func
        )


class StoreItem:

    registration_cls = Registration
    subscription_cls = Subscription
    type = None

    def __init__(self, store, uri):
        self.store = store
        self.uri = uri
        self.regs = WeakKeyDictionary()
        self.points = set()

    def __len__(self):
        return len(self.points)

    def __repr__(self):
        return "<{name} for '{uri}', type: '{type}'>".format(
            name=self.__class__.__name__,
            uri=self.uri, type=self.type
        )

    def add_point(self, node, func, is_source=False):
        if self.type == 'call' and len(self) > 0:
            raise ValueError('Uri already registered')
        result = RPCPoint(node, func, self, is_source=is_source)
        self.points.add(result)
        if self.store:
            self.store._index(self)
        return result

    def add_registration(self, reg):
        if reg.session in self.regs and self.regs[reg.session] != 'pending':
            raise ValueError("This item has a registration already")
        self.regs[reg.session] = reg
        if isinstance(reg, self.registration_cls):
            res = 'call'
        elif isinstance(reg, self.subscription_cls):
            res = 'subscription'
        else:
            raise ValueError("Registration type unknown")
        self.type = res
        if self.store:
            self.store._index(self)

    def add_registration_pending(self, session):
        if session in self.regs:
            raise ValueError("This item has a registration already")
        self.regs[session] = 'pending'

    def get_point(self, node, func):
        epd = RPCPoint(node, func, self)
        if epd not in self.points:
            raise KeyError('No points for that pair')
        return epd

    def empty(self, session=None):
        if session:
            l = len(set(rpc_point for rpc_point in self.points
                          if rpc_point.session is session))
        else:
            l = len(self.points)
        return l == 0

    def registration(self, session):
        return self.regs.get(session)

    def remove(self, node, func=None):
        if func:
            eplen = len(self.points)
            tgt = RPCPoint(node, func, self)
            self.points.remove(tgt)
            assert len(self.points) == eplen - 1
        else:
            for rpc_point in set(self.points):
                if rpc_point.node is node:
                    self.points.remove(rpc_point)
        if self.store:
            self.store._index(self, remove=True)

    async def unregister(self, session):
        res = None
        if self.regs and session in self.regs:
            reg = self.regs[session]
            if self.type == 'call':
                res = await reg.unregister()
            elif self.type == 'subscription':
                res = await reg.unsubscribe()
            del self.regs[session]
        return res


class RegistrationStore:

    def __init__(self, call_dispatcher, event_dispatcher):
        self.uri_to_item = {}
        self.node_to_items = {}
        self.call_dispatcher = call_dispatcher
        self.event_dispatcher = event_dispatcher

    def _index(self, item, remove=False):
        if remove:
            self._unindex(item)
        for rpc_point in item.points:
            if rpc_point.node not in self.node_to_items:
                self.node_to_items[rpc_point.node] = set()
            self.node_to_items[rpc_point.node].add(item)

    def _items_for_node(self, node):
        return self.node_to_items.get(node, set())

    def _unindex(self, item):
        for rpc_point in item.points:
            self._items_for_node(rpc_point.node).discard(item)

    async def add_call(self, node, context, *uri_funcs):
        """Register calls (procedures) with wamp. It expects ``uri_funcs``
        to be a tuple of ``(uri, func)`` items"""
        session = context.wamp_session
        opts = node.node_context.call_registration_options or \
               RegisterOptions(details_arg='details')
        coros = []
        results = []
        reg_items = []
        trans = transaction.get(None)
        for uri, func in uri_funcs:
            reg_item = self.get(uri)
            point = reg_item.add_point(node, func, is_source=True)
            results.append(point)
            reg_items.append(reg_item)
            dispatcher = partial(self.call_dispatcher, session, uri)
            coro = session.register(
                dispatcher,
                uri,
                options=opts
            )
            coros.append(coro)
        call_gathering = asyncio.gather(*coros,
                                        loop=context.loop)
        if trans:
            trans.add(call_gathering)
        regs = await call_gathering
        for ix, reg in enumerate(regs):
            reg_item = reg_items[ix]
            reg_item.add_registration(reg)
        return tuple(results)

    async def add_subscription(self, node, context, *uri_funcs):
        """Register handlers (subscriptions) with wamp. It expects ``uri_funcs``
        to be a tuple of ``(uri, func)`` items. Differently than the
        "call" conterpart, here the same uri can appear in more than one item,
        because it's possible to have multiple subscriptions per topic.
        """
        session = context.wamp_session
        opts = node.node_context.subscription_registration_options or \
               SubscribeOptions(details_arg='details')
        # trasform the ((uri, func),...) tuple into a dict[uri] = set((func,
        # func))
        uri_map = {}
        for ix, (uri, func, is_source) in enumerate(uri_funcs):
            if uri not in uri_map:
                uri_map[uri] = []
            uri_map[uri].append((ix, func, is_source))

        really_reg = []
        coros = []
        results = set()
        for uri, points in uri_map.items():
            for ix, func, is_source in points:
                reg_item = self.get(uri)
                point = reg_item.add_point(node, func, is_source=is_source)
                results.add((ix, point))
                if not reg_item.registration(session):
                    reg_item.add_registration_pending(session)
                    dispatcher = partial(self.event_dispatcher, session,
                                         RPCPoint(node), uri)
                    coro = session.subscribe(
                        dispatcher,
                        uri,
                        options=opts
                    )
                    really_reg.append(reg_item)
                    coros.append(coro)

        if coros:
            trans = transaction.get(None)
            call_gathering = asyncio.gather(*coros,
                                            loop=context.loop)
            if trans:
                trans.add(call_gathering)
            regs = await call_gathering
            for iy, reg in enumerate(regs):
                reg_item = really_reg[iy]
                reg_item.add_registration(reg)
        return tuple(zip(*sorted(results, key=lambda e: e[0])))[1]

    def clear(self):
        for item in set(self.uri_to_item.values()):
            self.expunge(item)

    def expunge(self, item):
        assert item in self.uri_to_item.values()
        self._unindex(item)
        del self.uri_to_item[item.uri]
        del item.store

    def get(self, uri):
        assert isinstance(uri, str)
        if uri not in self.uri_to_item:
            self.uri_to_item[uri] = StoreItem(self, uri)
        return self.uri_to_item[uri]

    async def remove(self, node, context, uri=None, func=None):
        if uri is None:
            assert func is None
        trans = transaction.get(None)
        unregs = set()
        session = context.wamp_session
        if uri:
            item = self.get(uri)
            item.remove(node, func)
            if item.empty(session):
                unregs.add(item)
            if item.empty():
                self.expunge(item)
        else:
            node_regs = self._items_for_node(node)
            for item in node_regs:
                item.remove(node)
                if item.empty(session):
                    unregs.add(item)
                if item.empty():
                    self.expunge(item)
        if unregs:
            coros = set(item.unregister(session) for item in unregs)
            gathering = asyncio.gather(*coros, loop=context.loop)
            if trans:
                trans.add(gathering)
            await gathering
