# -*- coding: utf-8 -*-
# :Project:   raccoon.rocky.node -- node class
# :Created:   mar 16 feb 2016 15:58:07 CET
# :Author:    Alberto Berti <alberto@metapensiero.it>
# :License:   GNU General Public License version 3 or later
# :Copyright: Copyright (C) 2016, 2017 Arstecnica s.r.l.
#

import logging

from metapensiero.signal import (Signal, SignalAndHandlerInitMeta)

from .context import NodeContext
from .path import Path
from .proxy import Proxy
from .wamp import WAMPInitMeta, AbstractWAMPNode
from . import serialize


_undefined = object()

logger = logging.getLogger(__name__)


class NodeError(Exception):
    """Error raised during node add/remove operations."""


class Node(metaclass=SignalAndHandlerInitMeta):
    """The node is the base building block of Rocky.
    """
    on_node_add = Signal(sequential_async_handlers=True)
    "Signal emitted when a node is added by setting an attribute to it."

    on_node_bind = Signal(sequential_async_handlers=True)
    """Signal emitted at the end of node_bind() call. Every callback will
    receive the following parameters:

    node : :class:`Node`
      the bound node

    path : :class:`~.path.Path`
      the path where the node is bound, available also as ``node.node_path``

    parent : :class:`Node`
      the parent node
    """

    on_node_unbind = Signal()
    """Signal emitted at the end of :meth:`node_unbind` call. Every callback
    will receive the same parameters as the `on_node_bind` signal.
    """

    node_context = None
    """An instance of the :class:`~.context.NodeContext` class that supplies
    informations for the :term:`WAMP` setup or possibly other kind of
    informations.
    """

    node_parent = None
    """Contains the parent node instance, if any."""

    node_path = None
    """After :meth:`bind` operation contains the :class:`~.path.Path` that
    describes the position in the tree and the base path for :term:`WAMP`
    functionality.
    """

    def __delattr__(self, name):
        """Deleting an attribute which has a node as value automatically will
        call :meth:`node_unbind` on it."""
        attr = getattr(self, name, None)
        if isinstance(attr, Node) and name != 'node_parent':
            raise NodeError("Cannot remove '%s', call node_remove() instead"
                            % name)
        super().__delattr__(name)

    def __setattr__(self, name, value):
        """Setting an attribute on a node that has a node as value handled so
        that it also binds the given node to the path of the parent
        node plus the name of the attribute as fragment.

        It fires the :attr:`on_node_add` event.
        """
        if (isinstance(value, Node) and name != 'node_parent' and
            value.node_path is None):
            raise NodeError("Cannot add '%s', call node_add() instead" % name)
        super().__setattr__(name, value)

    def __repr__(self):
        return "<%s at '%s'>" % (self.__class__.__name__, self.node_path)

    async def _node_after_bind(self, path, context=None, parent=None):
        pass

    async def _node_bind(self, path, context=None, parent=None):
        """`node_bind` alterable implementation."""
        if context is not None and isinstance(context, NodeContext):
            if self.node_context is None:
                self.node_context = context.new()
        self.node_path = Path(path)
        self.node_parent = parent
        if parent is not None and isinstance(parent, Node):
            parent.on_node_unbind.connect(self._node_on_parent_unbind)

    async def _node_on_parent_unbind(self, **_):
        self.node_parent.on_node_unbind.disconnect(self._node_on_parent_unbind)
        await self.node_unbind()

    def _node_remove_child(self, child):
        for k, v in self.__dict__.items():
            if v is child:
                break
        del self.__dict__[k]
        return k

    async def _node_unbind(self):
        """`node_unbind` alterable implementation"""
        del self.node_path
        if self.node_context is not None:
            del self.node_context
        if self.node_parent is not None:
            self.node_parent.on_node_unbind.disconnect(
                self._node_on_parent_unbind)
            del self.node_parent

    @property
    def loop(self):
        """Returns the asyncio loop for this node."""
        return self.node_context.loop if self.node_context is not None else None

    async def node_add(self, name, value):
        if not isinstance(value, Node):
            raise NodeError("Expected a Node as '%s', got: %r" % (name, value))
        assert value.node_parent is None
        path = self.node_path + name
        await value.node_bind(path, self.node_context, parent=self)
        await self.on_node_add.notify(path=path, node=value)
        value.on_node_unbind.connect(self.node_child_on_unbind)
        super().__setattr__(name, value)

    async def node_bind(self, path, context=None, parent=None):
        """Bind a node to a path, using the runtime context and optionally a
        parent. The context is cloned so that changes to it will affect only a
        branch.

        It emits an ``on_node_bind`` *synchronous* event with the following
        keyword arguments:

        node : :class:`Node`
          this node

        path : :class:`~.path.Path`
          this node's ``node_path``

        parent : :class:`Node`
          this node's ``node_parent``, if any

        :type path: an instance of :class:`~.path.Path`
        :param path: an instance of the path or a dotted string or a tuple.
        :type context: an instance of :class:`~.context.NodeContext`
        :param context: an instance of the current context or ``None``.
        :type parent: an instance of :class:`Node`
        :param parent: a parent node or ``None``.

        .. note:: This is now a *coroutine*

          This whas changed from a normal method (with transaction tracking)
          to a *coroutine*.

          In reason of this the ``on_node_bind`` was changed to be
          *synchronous*. This means that when this is complete, the
          notification of the event is completed too.
        """
        assert len(path) > 0
        await self._node_bind(path, context, parent)
        await self._node_after_bind(path, context, parent)
        await self.on_node_bind.notify(node=self,
                                       path=self.node_path,
                                       parent=self.node_parent)

    def node_child_on_unbind(self, node, path, parent):
        """Called when a child node unbind itself, by default it will remove
        the attribute reference on it.
        """
        self._node_remove_child(node)
        node.on_node_unbind.disconnect(self.node_child_on_unbind)

    @property
    def node_name(self):
        """Returns the name of this node, the last part of its path."""
        return self.node_path._path[-1] if self.node_path is not None else None

    async def node_remove(self, name):
        node = getattr(self, name, None)
        if node is None:
            raise NodeError("No node registered with name '%s' on %r"
                            % (name, self))
        if not isinstance(node, Node):
            raise NodeError("'%s' is not a Node" % name)
        if node.node_parent is self:
            await node.node_unbind()

    @property
    def node_root(self):
        """Returns the root of the tree."""
        if self.node_parent is not None:
            res = self.node_parent.node_root
        else:
            res = self
        return res

    async def node_unbind(self):
        """Unbinds a node from a path. It emits ``on_node_unbind`` event,
        without parameters.

        .. note:: This is now a *coroutine*

          This whas changed from a normal method (with transaction tracking)
          to a *coroutine*.
        """
        await self.on_node_unbind.notify(node=self,
                                         path=self.node_path,
                                         parent=self.node_parent)
        await self._node_unbind()


@serialize.define('raccoon.node.WAMPNode', allow_subclasses=True)
class WAMPNode(Node, serialize.Serializable, metaclass=WAMPInitMeta):
    """A Node subclass to deal with WAMP stuff. An instance gets
    local and WAMP pub/sub, WAMP RPC and automatic tree addressing.

    This is done by performing another two operations: *register* and
    *unregister* to be performed possibly at a different (later) time
    than the bind operation.

    This class is coded to run in tandem with the
    :class:`~.context.WAMPNodeContext` class that supplies the
    necessary informations about WAMP connection
    state. :meth:`node_register` should be called after the WAMP session
    has *joined* the Crossbar router.
    """

    node_registered = False
    """It's ``True`` if this mode's :meth:`node_register` has been called and
    that this node has successfully completed the registration process.
    """

    on_node_register = Signal()
    """Signal emitted when :meth:`node_register` is called. Its events have
    two keywords, ``node`` and ``context``.
    """

    on_node_registration_failure = Signal()
    """Signal emitted when registration fails. Its events have two keywords,
    ``node`` and ``context``.
    """

    on_node_registration_success = Signal()
    """Signal emitted when the registration is complete. Its events have two
    keywords, ``node`` and ``context``.
    """

    on_node_unregister = Signal()
    """Signal emitted when :meth:`node_unregister` is called. Its events have
    two keywords, ``node`` and ``context``.
    """

    async def _node_after_bind(self, path, context=None, parent=None):
        """Specialized to attach this node to the parent's
        :attr:`on_node_register` and :attr:`on_node_unbind` signals. It
        automatically calls :meth:`node_register`.
        """
        await super()._node_after_bind(path, context, parent)
        if parent is not None and isinstance(parent, WAMPNode):
            parent.on_node_register.connect(self._node_on_parent_register)
        await self.node_register()

    async def _node_on_parent_register(self, node, context):
        if self.node_context is None:
            self.node_context = context.new()
        await self.node_register()

    async def _node_unbind(self):
        """Specialized to call :meth:`node_unregister`."""
        await self.node_unregister()
        await super()._node_unbind()
        if self.node_registered:
            del self.node_registered

    def call(self, path, *args, **kwargs):
        """Call another rpc endpoint published via :term:`WAMP`.

        .. important::
          The ``disclose_me=True`` option (was the default in old
          ``raccoon.api`` framework) is now managed directly by
          crossbar in it's realm/role configuration.

        .. note::
          this isn't a coroutine but it returns one.
        """
        return self.__class__.manager.call(self, path, *args, **kwargs)

    @classmethod
    def node_deserialize(cls, value, endpoint_node):
        return endpoint_node.remote(value)

    async def node_register(self):
        """Register this node to the :term:`WAMP` session. It emits the
        :attr:`on_node_register` event."""
        if not self.node_registered and self.node_context is not None and \
           self.node_context.wamp_session is not None and \
           self.node_context.wamp_session.is_attached():
            await self.on_node_register.notify(node=self,
                                               context=self.node_context)

    @classmethod
    def node_serialize(cls, instance, srcpoint_node):
        if instance.node_path is None:
            raise serialize.SerializationError(
                "This instance cannot be serialized"
            )
        return serialize.Serialized(str(instance.node_path))

    async def node_unregister(self):
        """Unregisters the node from the :term:`WAMP` session. It emits the
        :attr:`on_node_unregister` event."""
        if self.node_registered:
            await self.on_node_unregister.notify(node=self,
                                                 context=self.node_context)

    def remote(self, path):
        return Proxy(self, path)


AbstractWAMPNode.register(WAMPNode)
