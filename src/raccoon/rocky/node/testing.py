# -*- coding: utf-8 -*-
# :Project:   raccoon.rocky.node -- testing utilities
# :Created:   mar 22 mar 2016 02:24:44 CET
# :Author:    Alberto Berti <alberto@metapensiero.it>
# :License:   GNU General Public License version 3 or later
# :Copyright: Copyright (C) 2016, 2017 Arstecnica s.r.l.
#

import asyncio

import pytest

from raccoon.rocky.node import NodeContext

@pytest.fixture(scope='function')
def node_context(event_loop):
    return NodeContext(
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
