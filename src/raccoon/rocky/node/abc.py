# -*- coding: utf-8 -*-
# :Project:   raccoon.rocky.node -- WAMP Node abc
# :Created:   mer 18 ott 2017 19:51:50 CEST
# :Author:    Alberto Berti <alberto@metapensiero.it>
# :License:   GNU General Public License version 3 or later
# :Copyright: Copyright © 2017 Arstecnica s.r.l.
#

from abc import ABCMeta, abstractmethod, abstractproperty

from metapensiero.signal import Signal

class AbstractNode(metaclass=ABCMeta):

    on_node_add = abstractproperty()
    on_node_after_unbind = abstractproperty()
    on_node_before_bind = abstractproperty()
    on_node_bind = abstractproperty()
    on_node_register = abstractproperty()
    on_node_unbind = abstractproperty()
    on_node_unregister = abstractproperty()

    @abstractmethod
    async def node_add(self, name, value):
        """Adds an binds a node as a child with the supplied name."""

    @abstractmethod
    async def node_bind(self, path, context=None, parent=None):
        """Bind a node to a `path`, using the runtime `context` and optionally
        a `parent`."""

    @property
    @abstractmethod
    def node_name(self):
        """Returns the name of this node, the last part of its path."""

    @abstractmethod
    async def node_remove(self, name):
        """Removes a child node."""

    @property
    @abstractmethod
    def node_root(self):
        """Returns the root of the tree."""

    @abstractmethod
    async def node_unbind(self):
        """Unbinds a node from a path. It emits a `on_node_unbind` event,
        without parameters."""

    @classmethod
    def __subclasshook__(cls, subcls):
        from .signal import NodeInitMeta
        result = False
        if issubclass(type(subcls), NodeInitMeta):
            for name in ('on_node_add', 'on_node_after_unbind',
                         'on_node_before_bind', 'on_node_bind',
                         'on_node_register', 'on_node_unbind',
                         'on_node_unregister'):
                if not any((name in b.__dict__ and
                            isinstance(getattr(b, name), Signal))
                            for b in subcls.__mro__):
                    break
            else:
                result = True
        return result


class AbstractDispatcher(metaclass=ABCMeta):

    def __init__(self):
        self.gateways = set()

    def add_gateway(self, instance):
        """Adds a gateway to this dispatcher."""
        if not isinstance(instance, AbstractGateway):
            raise ValueError("Gateway must be an instance of AbstractGateway"
                             " got %r instead" % type(instance))
        self.gateways.add(instance)

    def remove_gateway(self, instance):
        """Remove a gateway from a dispatcher."""
        self.gateways.discard(instance)

    @abstractmethod
    def dispatch(self, dispatch_details):
        """Dispatch the data specified into the `dispatch_details` parameter."""


class AbstractGateway(metaclass=ABCMeta):

    remote = abstractproperty()
    """Tells if this gateway interfaces with an external system."""

    @abstractmethod
    def connect(self, node_context):
        """Connect a `~.context.NodeContext` to this gateway"""

    @property
    @abstractmethod
    def contexts(self):
        """Returns the contexts connected to this gateway."""

    @abstractmethod
    def dispatch(self, dispatcher, dispatch_details):
        """Apply a dispatching to all the participant contextes."""
