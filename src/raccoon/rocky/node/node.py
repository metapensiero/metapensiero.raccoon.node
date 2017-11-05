# -*- coding: utf-8 -*-
# :Project:   raccoon.rocky.node -- node class
# :Created:   mar 16 feb 2016 15:58:07 CET
# :Author:    Alberto Berti <alberto@metapensiero.it>
# :License:   GNU General Public License version 3 or later
# :Copyright: Copyright (C) 2016, 2017 Arstecnica s.r.l.
#

import asyncio
import logging

from metapensiero.signal import MultipleResults, Signal

from .abc import AbstractNode
from .context import NodeContext
from .errors import NodeError
from .path import Path
from .registry import CallKey, HandlerKey, SignalKey
from .signal import NodeInitMeta
from . import utils


_undefined = object()

logger = logging.getLogger(__name__)


class Node(AbstractNode, metaclass=NodeInitMeta):
    """The node is the base building block of Rocky.
    """

    "Non-addressable signal names."
    INTERNAL_SIGNALS = {
        'on_node_before_bind',
        'on_node_after_unbind'
    }

    on_node_add = Signal()
    """Signal emitted when a node is added by setting an attribute to it.
    Every callback will receive the following parameters:

    node : :class:`Node`
      the bound node

    path : :class:`~.path.Path`
      the path where the node is bound, available also as ``node.node_path``
    """

    on_node_after_unbind = Signal(sort_mode=Signal.SORT_MODE.TOPDOWN)
    """Signal emitted at the end of :meth:`node_unbind` call, after
    `on_node_bind. Every callback
    will receive the following parameters:

    node : :class:`Node`
      the bound node

    path : :class:`~.path.Path`
      the path where the node is bound, available also as ``node.node_path``

    parent : :class:`Node`
      the parent node
    """

    on_node_before_bind = Signal()
    """Signal emitted at the start of :meth:`node_bind` call. Every callback
    will receive the following parameters:

    node : :class:`Node`
      the bound node

    path : :class:`~.path.Path`
      the path where the node is bound, available also as ``node.node_path``

    parent : :class:`Node`
      the parent node
    """

    on_node_bind = Signal()
    """Signal emitted at the end of :meth:`node_bind` call. Every callback
    will receive the following parameters:

    node : :class:`Node`
      the bound node

    path : :class:`~.path.Path`
      the path where the node is bound, available also as ``node.node_path``

    parent : :class:`Node`
      the parent node
    """

    on_node_register = Signal()

    on_node_unbind = Signal(sort_mode=Signal.SORT_MODE.TOPDOWN)
    """Signal emitted at the end of :meth:`node_unbind` call. Every callback
    will receive the following parameters:

    node : :class:`Node`
      the bound node

    path : :class:`~.path.Path`
      the path where the node is bound, available also as ``node.node_path``

    parent : :class:`Node`
      the parent node
    """

    on_node_unregister = Signal(sort_mode=Signal.SORT_MODE.TOPDOWN)

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

    _node_unbind_task = None
    """Track if an unbind has started already."""

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

    async def _node_after_unbind(self):
        await self.on_node_after_unbind.notify(node=self,
                                               path=self.node_path,
                                               parent=self.node_parent)

    async def _node_before_bind(self, path, context=None, parent=None):
        if context is not None and isinstance(context, NodeContext):
            if self.node_context is None:
                context = context.new()
            else:
                context = self.node_context
        elif ((context is None or not isinstance(context, NodeContext)) and
              self.node_context is None):
            raise NodeError("Missing context")
        if not isinstance(path, Path):
            path = Path(path)
        await self._node_register(path, context, parent)
        return path, context

    async def _node_bind(self, path, context, parent=None):
        """`node_bind` alterable implementation."""
        self.node_path = path
        self.node_context = context
        self.node_parent = parent
        if parent is not None and isinstance(parent, Node):
            parent.on_node_unbind.connect(self._node_on_parent_unbind)

    async def _node_on_parent_unbind(self, **_):
        self.node_parent.on_node_unbind.disconnect(self._node_on_parent_unbind)
        await self.node_unbind()

    async def _node_register(self, path, context, parent=None):
        registry = context.registry
        logger.debug("Beginning binding of: node at %r resources", path)
        signals_data = utils.filter_signals(type(self)._signals,
                                            self.INTERNAL_SIGNALS)
        handlers_data = type(self)._node_handlers
        calls_data = type(self)._node_calls
        points = set()
        if len(signals_data):
            try:
                for name, sig in signals_data.items():
                    sig_path = utils.calc_signal_path(path, sig, name)
                    points.add(registry.add_point(sig_path,
                                                  SignalKey(self, sig).point()))
            except Exception as e:
                if __debug__:
                    logger.exception("Error while binding signals")
                else:
                    logger.error("Error while binding signals")
                raise NodeError("Error while binding signals") from e
        if len(handlers_data):
            try:
                handler_endpoints = utils.build_instance_mapping(self,
                                                                 handlers_data)
                for name, meth in handler_endpoints.items():
                    hand_path = utils.calc_handler_target_path(path, context,
                                                               name)
                    points.add(registry.attach_point(
                        hand_path, HandlerKey(self, meth).point()))
            except Exception as e:
                if __debug__:
                    logger.exception("Error while binding handlers")
                else:
                    logger.error("Error while binding handlers")
                raise NodeError("Error while binding handlers") from e
        if len(calls_data):
            try:
                call_endpoints = utils.build_instance_mapping(self,
                                                              calls_data)
                for name, meth in call_endpoints.items():
                    hand_path = utils.calc_call_path(path, context, name)
                    points.add(registry.attach_point(hand_path,
                        CallKey(self, meth).point()))
            except Exception as e:
                if __debug__:
                    logger.exception("Error while binding calls")
                else:
                    logger.error("Error while binding calls")
                raise NodeError("Error while binding calls") from e
        try:
            points = frozenset(await MultipleResults(points))
        except Exception as e:
            if __debug__:
                logger.exception("Error while binding endpoints")
            else:
                logger.error("Error while binding endpoints")
            raise NodeError("Error while binding endpoints") from e
        logger.debug("Completed binding of signals, handlers and calls on "
                     "node at %r", path)
        await self.on_node_register.notify(
            node=self, path=path, context=context, parent=parent, points=points)
        return points

    def _node_remove_child(self, child):
        for k, v in self.__dict__.items():
            if v is child:
                break
        del self.__dict__[k]
        return k

    async def _node_unbind(self):
        """`node_unbind` alterable implementation"""
        if self.node_parent is not None:
            self.node_parent.on_node_unbind.disconnect(
                self._node_on_parent_unbind)
        await self._node_unregister()

    def _node_unbind_cleanup(self):
        del self.node_path
        if self.node_context is not None:
            del self.node_context
        if self.node_parent is not None:
            del self.node_parent

    async def _node_unbind_inner(self):
        await self.on_node_unbind.notify(
            node=self, path=self.node_path, parent=self.node_parent)
        await self._node_unbind()
        await self._node_after_unbind()
        self._node_unbind_cleanup()

    async def _node_unregister(self):
        registry = self.node_context.registry
        points = registry.points_for_owner(self)
        detached_points = await MultipleResults(registry.detach_point(p)
                                                for p in points)
        await self.on_node_unregister.notify(
            node=self, path=self.node_path, context=self.node_context,
            parent=self.node_parent, points=detached_points)
        return points

    @property
    def loop(self):
        """Returns the asyncio loop for this node."""
        return self.node_context.loop if self.node_context is not None else None

    async def node_add(self, name, value):
        """Adds an binds a node as a child with the supplied name."""
        if not isinstance(value, Node):
            raise NodeError("Expected a Node as '%s', got: %r" % (name, value))
        assert value.node_parent is None
        path = self.node_path + name
        await value.node_bind(path, self.node_context, parent=self)
        await self.on_node_add.notify(path=path, node=value)
        value.on_node_unbind.connect(self.node_child_on_unbind)
        super().__setattr__(name, value)

    async def node_bind(self, path, context=None, parent=None):
        """Bind a node to a `path`, using the runtime `context` and optionally
        a `parent`. The context is cloned so that changes to it will affect
        only a branch.

        It emits a `on_node_bind` *synchronous* event with the following
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

          This was changed from a normal method (with transaction tracking)
          to a *coroutine*.

          In reason of this the ``on_node_bind`` was changed to be
          *synchronous*. This means that when this is complete, the
          notification of the event is completed too.
        """
        assert len(path) > 0
        path, context = await self._node_before_bind(path, context, parent)
        await self.on_node_before_bind.notify(node=self,
                                              path=path,
                                              parent=parent)
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
        """Removes a child node."""
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
        """Unbinds a node from a path. It emits a `on_node_unbind` event,
        without parameters.
        """
        if self.node_path is None and self._node_unbind_task is None:
            raise NodeError("Trying to unbind a not bound node")
        if self._node_unbind_task is None:
            self._node_unbind_task = asyncio.ensure_future(
                self._node_unbind_inner())
        await self._node_unbind_task
