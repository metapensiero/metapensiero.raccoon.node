# -*- coding: utf-8 -*-
# :Project:   raccoon.rocky.node -- testing utilities
# :Created:   mar 22 mar 2016 02:24:44 CET
# :Author:    Alberto Berti <alberto@metapensiero.it>
# :License:   GNU General Public License version 3 or later
# :Copyright: Copyright (C) 2016, 2017 Arstecnica s.r.l.
#

import asyncio
import json
from unittest import mock

import pytest

from raccoon.rocky.node import context
from raccoon.rocky.node.wamp import node_wamp_manager


class FakeCallDetails:
    def __init__(self, progress, caller, caller_authid, procedure):
        self.progress = progress
        self.caller = caller
        self.caller_authid = caller_authid
        self.procedure = procedure


class FakeEventDetails:
    def __init__(self, publication, publisher, publisher_authid, topic):
        self.publication = publication
        self.publisher = publisher
        self.publisher_authid = publisher_authid
        self.topic = topic


class FakeRegistration:

    def __init__(self, session, procedure, delfunc):
        self.procedure = procedure
        self.active = True
        self._delfunc = delfunc
        self.session = session

    async def unregister(self):
        self._delfunc(self.procedure)


class FakeSubscription:

    def __init__(self, session, topic, handler, delfunc):
        self.topic = topic
        self.handler = handler
        self.active = True
        self._delfunc = delfunc
        self.session = session

    async def unsubscribe(self):
        self._delfunc(self.topic, self.handler)


def create_fake_session(global_registry, event_loop):
    registered_procs = {}
    registered_handlers = {}

    def _unregister(procedure):
        del registered_procs[procedure]

    def _unsubscribe(topic, handler):
        registered_handlers[topic].remove(handler)

    async def call(name, *args, **kwargs):
        if name == 'wamp.session.get':
            # simulate call to crossbar session info getter
            result = {
                'authid': '<a_fake_id>'
            }
        else:
            args, kwargs = json.dumps(args), json.dumps(kwargs)
            result = await global_registry.call(fake_session, name, args, kwargs)
            assert isinstance(result, str)
            result = json.loads(result)
        return result

    async def register(func, name, options=None):
        registered_procs[name] = {
            'func': func,
            'options': options
        }
        fake_session.last_register_opts.return_value = options
        return FakeRegistration(fake_session, name, _unregister)

    async def subscribe(func, topic, options=None):
        # just a simple exact subscription for now
        registered_handlers.setdefault(topic, set()).add(func)
        fake_session.last_subscribe_opts.return_value = options
        return FakeSubscription(fake_session, topic, func, _unsubscribe)

    def publish(topic, *args, **kwargs):
        if 'options' in kwargs:
            kwargs.pop('options')
        args, kwargs = json.dumps(args), json.dumps(kwargs)
        global_registry.publish(fake_session, topic, args, kwargs)

    def dispatch_publish(topic, args, kwargs):
        subscribers = registered_handlers.get(topic)
        if subscribers:
            edetails = FakeEventDetails(87654321,  # publication id
                                        publisher=12345678,
                                        publisher_authid='mock_publisher',
                                        topic=topic)
            fake_session.last_publish_details.return_value = edetails
            args, kwargs = json.loads(args), json.loads(kwargs)
            for handler in subscribers:
                # always add publisher's data as if the publisher specified
                # disclose_me=True
                result = handler(*args,
                                 details=edetails,
                                 **kwargs)
                # if handler is a coro, schedule but do not wait for result
                if asyncio.iscoroutine(result):
                    asyncio.ensure_future(result, loop=event_loop)

    async def dispatch_call(name, args, kwargs):
        # simplified dispatch, exact or wildcard at the end:
        # i.e. 'raccoon.api.pippo.pluto' or 'raccoon.api.pippo.'
        chosen = ''
        if name in registered_procs:
            chosen = registered_procs[name]['func']
        else:
            candidates = [k for k in registered_procs.keys() if
                          k.endswith('.')]
            for c in candidates:
                if name.startswith(c) and \
                   len(name.split('.')) == len(c.split('.')) and \
                   len(c) > len(chosen):
                    chosen = c

            if chosen:
                chosen = registered_procs[chosen]['func']
        if chosen and callable(chosen):
            # always inject calldetails into the "details" kw
            call_details = FakeCallDetails(progress=None, caller=12345678,
                                           caller_authid='mock_caller',
                                           procedure=name)

            args, kwargs = json.loads(args), json.loads(kwargs)
            result = chosen(*args, details=call_details, **kwargs)
            if asyncio.iscoroutine(result):
                result = await result
            fake_session.last_calldetails.return_value = call_details
        else:
            # TODO: should raise a proper autobahn error
            raise ValueError('Procedure "{}" is not registered'.format(name))
        result = json.dumps(result)
        return result

    fake_session = mock.NonCallableMock()
    fake_session.call.side_effect = call
    fake_session.register.side_effect = register
    fake_session.subscribe.side_effect = subscribe
    fake_session.publish.side_effect = publish
    fake_session.is_attached.return_value = True
    fake_session._procs.return_value = registered_procs
    fake_session._subs.return_value = registered_handlers
    fake_session.dispatch_publish.side_effect = dispatch_publish
    fake_session.dispatch_call.side_effect = dispatch_call
    fake_session.procs = registered_procs
    fake_session.subs = registered_handlers
    global_registry.add(fake_session)
    return fake_session


class GlobalRegistry:

    def __init__(self):
        self.sessions = set()

    def add(self, session):
        self.sessions.add(session)

    def publish(self, session, topic, args, kwargs):
        other_sessions = self.sessions - set((session,))
        for sess in other_sessions:
            sess.dispatch_publish(topic, args, kwargs)

    async def call(self, session, uri, args, kwargs):
        for sess in self.sessions:
            try:
                res = await sess.dispatch_call(uri, args, kwargs)
                break
            except ValueError:
                pass
        else:
            raise ValueError('Procedure "{}" is not registered'.format(uri))
        return res


@pytest.fixture(scope='function')
def global_registry():
    return GlobalRegistry()


@pytest.fixture(scope='function')
def wamp_session(request, event_loop, global_registry):

    fake_session = create_fake_session(global_registry, event_loop)
    # Monkey patch registrationitem to make unregistration work
    from . import registrations as regmod
    _old_reg_cls = regmod.StoreItem.registration_cls
    _old_sub_cls = regmod.StoreItem.subscription_cls
    regmod.StoreItem.registration_cls = FakeRegistration
    regmod.StoreItem.subscription_cls = FakeSubscription
    node_wamp_manager.clear()
    yield fake_session
    regmod.StoreItem.registration_cls = _old_reg_cls
    regmod.StoreItem.subscription_cls = _old_sub_cls


@pytest.fixture(scope='function')
def wamp_session2(request, event_loop, global_registry):
    fake_session = create_fake_session(global_registry, event_loop)
    return fake_session


@pytest.fixture(scope='function')
def wamp_context(wamp_session, event_loop):
    return context.WAMPNodeContext(
        event_loop,
        wamp_session=wamp_session
    )


@pytest.fixture(scope='function')
def wamp_context2(wamp_session2, event_loop):
    return context.WAMPNodeContext(
        event_loop,
        wamp_session=wamp_session2
    )


@pytest.fixture(scope='function')
def node_context(event_loop):
    return context.NodeContext(
        event_loop
    )


class EventFactory:
    """An helper class that helps creating asyncio.Event instances and
    waiting for them.
    """

    def __init__(self, loop=None):
        self.loop = loop
        self.events = set()

    def __getattr__(self, name):
        event = asyncio.Event(loop=self.loop)
        setattr(self, name, event)
        self.events.add(event)
        return event

    def __getitem__(self, name):
        event = self.__dict__.get(name)
        if event is None:
            event = getattr(self, name)
        return event

    def wait(self, *exclude, timeout=None):
        exclude = set(exclude)
        return asyncio.wait(
            map(lambda e: e.wait(),
            self.events - exclude), timeout=timeout,
            loop=self.loop)

    def reset(self):
        for e in self.events:
            e.clear()

    def define(self, *names):
        for name in names:
            getattr(self, name)

    def wait_for(self, event, timeout=None):
        return asyncio.wait_for(event.wait(), timeout=timeout, loop=self.loop)

    TimeoutError = asyncio.TimeoutError


@pytest.fixture(scope='function')
def events(event_loop):
    return EventFactory(event_loop)
