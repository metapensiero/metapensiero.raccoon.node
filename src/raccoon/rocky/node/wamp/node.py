# -*- coding: utf-8 -*-
# :Project:   raccoon.rocky.node -- WAMP specific node implementation
# :Created:   mer 18 ott 2017 19:51:50 CEST
# :Author:    Alberto Berti <alberto@metapensiero.it>
# :License:   GNU General Public License version 3 or later
# :Copyright: Copyright © 2016, 2017 Arstecnica s.r.l.
#

from metapensiero.signal import Signal

from ..node import Node
from .proxy import Proxy
from .. import serialize

from .abc import AbstractWAMPNode
from .signal import WAMPInitMeta


@serialize.define('raccoon.node.WAMPNode', allow_subclasses=True)
class WAMPNode(Node, serialize.Serializable, metaclass=WAMPInitMeta):
    """A Node subclass to deal with WAMP stuff. An instance gets
    local and WAMP pub/sub, WAMP RPC and automatic tree addressing.

    This is done by performing other two operations: *register* and
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
        `on_node_register` event."""
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
        `on_node_unregister` event."""
        if self.node_registered:
            await self.on_node_unregister.notify(node=self,
                                                 context=self.node_context)

    def remote(self, path):
        "Return a :class:`~.proxy.Proxy` instance on the given `path`."
        return Proxy(self, path)


AbstractWAMPNode.register(WAMPNode)
