# -*- coding: utf-8 -*-
# :Project:   raccoon.rocky.node -- node context
# :Created:   mar 16 feb 2016 18:10:22 CET
# :Author:    Alberto Berti <alberto@metapensiero.it>
# :License:   GNU General Public License version 3 or later
# :Copyright: Copyright (C) 2016 Arstecnica s.r.l.
#

import asyncio

undefined = object


class NodeContext:
    """The run context of a tree of :py:class:`raccoon.rocky.node.Node`
    instances.
    """

    def __init__(self, loop=None, path_resolvers=None):
        self._parent_context = None
        self.loop = loop or asyncio.get_event_loop()
        self.path_resolvers = path_resolvers or []

    def __contains__(self, item):
        return getattr(self, item, undefined) is not undefined

    def __getattr__(self, name):
        ctx = self._parent_context
        while ctx:
            value = ctx.__dict__.get(name, undefined)
            if value is not undefined:
                break
            ctx = ctx._parent_context
        else:
            raise AttributeError
        return value

    def __iter__(self):
        return iter(self.keys())

    def get(self, name, default=None):
        return getattr(self, name, default)

    def keys(self):
        keys = self.__dict__.keys() - {'_parent_context'}
        if self._parent_context:
            keys |= self._parent_context.keys()
        return keys

    def items(self):
        for k in self.keys():
            yield (k, getattr(self, k))

    def new(self, **kwargs):
        """Poor man's prototype inheritation. This returns a new instance of
        NodeContext with data *chained* to this one. Non passed in values will
        be inherited from the instance where this method is called."""
        nc = self.__new__(type(self))
        nc._parent_context = self
        for k, v in kwargs.items():
            setattr(nc, k, v)
        return nc

    def chain(self, other):
        if not self._parent_context:
            self._parent_context = other
        else:
            raise ValueError("Already chained")

    def set(self, name, value):
        setattr(self, name, value)


class WAMPNodeContext(NodeContext):
    """A Node context with WAMP management details."""

    def __init__(self, loop=None, path_resolvers=None, wamp_session=None,
                 wamp_details=None, publication_wrapper=None,
                 subscription_wrapper=None, call_wrapper=None,
                 call_registration_options=None,
                 subscription_registration_options=None):
        super().__init__(loop=loop, path_resolvers=path_resolvers)
        self.wamp_session = wamp_session
        self.wamp_details = wamp_details
        self.publication_wrapper = publication_wrapper
        self.subscription_wrapper = subscription_wrapper
        self.call_wrapper = call_wrapper
        self.call_registration_options = call_registration_options
        self.subscription_registration_options = subscription_registration_options
