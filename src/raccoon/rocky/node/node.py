# -*- coding: utf-8 -*-
# :Project:   raccoon.rocky.node -- node class
# :Created:   mar 16 feb 2016 15:58:07 CET
# :Author:    Alberto Berti <alberto@metapensiero.it>
# :License:   GNU General Public License version 3 or later
# :Copyright: Copyright (C) 2016 Arstecnica s.r.l.
#

import inspect
import logging

from metapensiero.signal import (Signal, SignalAndHandlerInitMeta)

from .context import NodeContext
from .path import Path
from .proxy import Proxy
from . import utils
from .wamp import WAMPInitMeta, AbstractWAMPNode

_undefined = object()

logger = logging.getLogger(__name__)


class Node(metaclass=SignalAndHandlerInitMeta):
    """The node is the base building block of Rocky.
    """
    on_node_add = Signal()
    "Signal emitted when a node is added by setting an attribute to it."

    on_node_bind = Signal()
    "Signal emitted at the end of node_bind() call."

    on_node_unbind = Signal()
    "Signal emitted at the end of node_unbind() call."

    node_context = None
    """An instance of the
    :py:class:`raccoon.rocky.node.context.NodeContext` class that
    supplies informations for the :term:`WAMP` setup or possibly other
    kind of informations.
    """

    node_parent = None
    """Contains the parent node instance, if any."""

    node_path = None
    """After ``bind()`` operation contains the
    :py:class:`raccoon.rocky.node.path.Path` that describes the
    position in the tree and the base path for :term:`WAMP`
    functionality.
    """

    def __delattr__(self, name):
        """Deleting an attribute which has a node as value automatically will
        call :meth:`node_unbind` on it."""
        attr = getattr(self, name, None)
        if name != 'node_parent' and isinstance(attr, Node):
            attr.node_unbind()
        else:
            super().__delattr__(name)

    def __setattr__(self, name, value):
        """Setting an attribute on a node that has a node as value handled so
        that it also binds the given node to the path of the parent
        node plus the name of the attribute as fragment.

        It fires the ``on_node_add`` event.
        """
        if isinstance(value, Node) and name != 'node_parent':
            path = self.node_path + name
            value.node_bind(path, self.node_context, parent=self)
            res = self.on_node_add.notify(path=path, node=value)
            if inspect.isawaitable(res):
                # in some tests this is not true
                res = utils.add_to_transaction(res, loop=self.loop)
            value.on_node_unbind.connect(self.node_child_on_unbind)
        super().__setattr__(name, value)

    def __str__(self):
        return "%s instance at '%s''" % (self.__class__.__name__,
                                         self.node_path)

    def _node_on_parent_unbind(self, **_):
        self.node_parent.on_node_unbind.disconnect(self._node_on_parent_unbind)
        self.node_unbind()

    def _node_remove_child(self, child):
        for k, v in self.__dict__.items():
            if v is child:
                break
        del self.__dict__[k]

    @property
    def loop(self):
        """Returns the asyncio loop for this node."""
        return self.node_context.loop if self.node_context else None

    def node_bind(self, path, context=None, parent=None):
        """Bind a node to a path, using the runtime context and optionally a
        parent. The context is cloned so that changes to it will affect only a
        branch.

        It emits an ``on_node_bind`` event with the the following
        keyword arguments:

        node:
          this node
        path:
          this node's ``node_path``
        parent:
          this node's ``node_parent``, if any

        :param path: and instance of the path or a dotted string or a tuple.
        :param context: an instance of the current context or `None`.
        :param parent: a parent node or `None`.
        :type path: an instance of :class:`~raccoon.rocky.node.path.Path`
        :type context: an instance of
          :class:`~raccoon.rocky.node.context.NodeContext`
        :type parent: an instance of :class:`~.Node`
        """
        assert len(path) > 0
        if context and isinstance(context, NodeContext):
            if not self.node_context:
                self.node_context = context.new()
        self.node_path = Path(path)
        self.node_parent = parent
        if parent and isinstance(parent, Node):
            parent.on_node_unbind.connect(self._node_on_parent_unbind)
        res = self.on_node_bind.notify(node=self,
                                       path=self.node_path,
                                       parent=self.node_parent)
        if inspect.isawaitable(res):
            # in some tests this is not true
            res = utils.add_to_transaction(res, loop=self.loop)

    def node_child_on_unbind(self, node, path, parent):
        """Called when a child node unbind itself, by default it will remove the
        attribute reference on it.
        """
        self._node_remove_child(node)
        node.on_node_unbind.disconnect(self.node_child_on_unbind)

    @property
    def node_name(self):
        """Returns the name of this node, the last part of its path."""
        return self.node_path._path[-1] if self.node_path else None

    @property
    def node_root(self):
        """Returns the root of the tree."""
        return self.node_parent.node_root if self.node_parent else self

    def node_unbind(self):
        """Unbinds a node from a path. It emits ``on_node_unbind`` event."""
        res = self.on_node_unbind.notify(node=self,
                                         path=self.node_path,
                                         parent=self.node_parent)
        if inspect.isawaitable(res):
            # in some tests this is not true
            res = utils.add_to_transaction(res, loop=self.loop)
        del self.node_path
        if self.node_context:
            del self.node_context
        if self.node_parent:
            del self.node_parent


class WAMPNode(Node, metaclass=WAMPInitMeta):
    """A Node subclass to deal with WAMP stuff. An instance gets
    local and wamp pub/sub, wamp rpc and automatic tree addressing.

    This is done by performing another two operations: *register* and
    *unregister* to be performed possibly at a different (later) time
    than the bind operation.

    This class is coded to run in tandem with the
    :py:class:`.context.WAMPNodeContext` class that supplies the
    necessary informations about WAMP connection
    state. ``node_register()`` should be called after the WAMP session
    has *joined* the Crossbar router.
    """

    node_registered = False
    """It's t ``True`` if this mode's node_register() has been called and that
    this node has successfully completed the registration process.
    """

    on_node_register = Signal()
    """Signal emitted when node_register() is called. Its events have two
    keywords, ``node`` and ``context``.
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
    """Signal emitted when node_unregister() is called. Its events have two
    keywords, ``node`` and ``context``.
    """

    def _node_on_parent_register(self, node, context):
        if not self.node_context:
            self.node_context = context.new()
        self.node_register()

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

    def node_bind(self, path, context=None, parent=None):
        """Specialized to attach this node to the parent's
        ``on_node_register`` and ``on_node_unbind`` signals. It
        automatically calls :meth:`.node_register`.
        """
        super().node_bind(path, context, parent)
        if parent and isinstance(parent, WAMPNode):
            parent.on_node_register.connect(self._node_on_parent_register)
        self.node_register()

    def node_register(self):
        """Register this node to the :term:`WAMP` session. It emits the
        ``on_node_register`` event."""
        if not self.node_registered and self.node_context and \
           self.node_context.wamp_session and \
           self.node_context.wamp_session.is_attached():
            res = self.on_node_register.notify(node=self,
                                               context=self.node_context)
            res = utils.add_to_transaction(res, loop=self.loop)

    def node_unbind(self):
        """Specialized to call :meth:`.node_unregister`."""
        def when_unregistered(future=None):
            with utils.in_transaction(loop=self.loop, task=future):
                super(WAMPNode, self).node_unbind()
                if self.node_registered:
                    del self.node_registered

        maybe_future = self.node_unregister()
        if inspect.isawaitable(maybe_future):
            maybe_future = utils.add_to_transaction(maybe_future, loop=self.loop)
            maybe_future.add_done_callback(when_unregistered)
        else:
            when_unregistered()

    def node_unregister(self):
        """Unregisters the node from the :term:`WAMP` session. It emits the
        ``on_node_unregister`` event."""
        if self.node_registered:
            res = self.on_node_unregister.notify(node=self,
                                                 context=self.node_context)
            res = utils.add_to_transaction(res, loop=self.loop)
        else:
            res = None
        return res

    def remote(self, path):
        return Proxy(self, path)

AbstractWAMPNode.register(WAMPNode)
