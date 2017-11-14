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
