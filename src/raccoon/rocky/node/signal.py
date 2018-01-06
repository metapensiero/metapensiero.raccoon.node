# -*- coding: utf-8 -*-
# :Project:   raccoon.rocky.node -- metapensiero.signal hookup
# :Created:   mar 24 ott 2017 16:05:44 CEST
# :Author:    Alberto Berti <alberto@metapensiero.it>
# :License:   GNU General Public License version 3 or later
# :Copyright: Copyright © 2016, 2017, 2018 Alberto Berti
#

import logging

from metapensiero.signal import (ExternalSignallerAndHandler,
                                 SignalAndHandlerInitMeta, NoResult)


from .abc import AbstractNode
from .deco import CallNameDecorator
from .dispatch import DispatchDetails
from .errors import NodeError
from .registry import SignalKey, RPCType

from . import utils

logger = logging.getLogger(__name__)


class NodeBridge(ExternalSignallerAndHandler):
    """Hooks into ``metapensiero.signal`` machinery and registers itelf to
    handle path resolving, mostly."""

    def publish_signal(self, signal, instance, loop, args, kwargs):
        """Signal API. Publish a signal. The path is the
        node's path + the signal name.

        """
        sname = signal.name
        if sname in instance.INTERNAL_SIGNALS or instance.node_path is None:
            return NoResult

        # mangle kwargs to expunge those to begin with 'local_', this
        # way the notifier can still add non JSON-encodable object as
        # params while being sure that this will not cause an error
        # during WAMP publication
        # ext_kwargs = {k: v for k, v in kwargs.items()
        #               if not k.startswith('local_')}
        src_point = SignalKey(instance, signal).point()
        if src_point.is_attached:
            dispatcher = instance.node_context.dispatcher
            details = DispatchDetails(
                RPCType.EVENT, src_point,
                utils.calc_signal_path(instance.node_path,
                                       instance.node_context, signal.name),
                args=args, kwargs=kwargs)
            return dispatcher.dispatch(details)
        else:
            return NoResult

    def register_class(self, cls, bases, namespace, signals, handlers):
        """Signal API. This is called by SignalAndHandlerInitMeta.

        It finds event, event handlers defined in the body of this
        class bases using utilities provided by the SignalAndHandlerInitMeta
        class.

        Then connects ``on_node_bind`` and ``on_node_unbind`` signals to to
        this instance handlers.

        Finally saves all the data on the class.
        """
        nsubs, ncalls = cls._build_inheritance_chain(
            bases, '_node_handlers', '_node_calls', merge=True)

        # find calls
        for aname, avalue in namespace.items():
            call_name = CallNameDecorator.is_call(aname, avalue)
            if call_name:
                ncalls[aname] = call_name
            elif call_name is None:
                ncalls[aname] = aname

        # connect to signals
        # class is constructed already
        if issubclass(cls, AbstractNode):
            # filter handlers
            new_nsubs = {}
            for hname, sig_name in handlers.items():
                if sig_name not in signals:
                    new_nsubs[hname] = sig_name
            for hname in new_nsubs.keys():
                del handlers[hname]
            nsubs.update(new_nsubs)
        else:
            logger.warning("Not registering class %s.%s as it doesn't "
                           " implement AbstractNode", cls.__module__,
                           cls.__name__)
        cls._node_handlers = nsubs
        cls._node_calls = ncalls
        logger.debug("Scanned class %s.%s for RPC points, found "
                     "%d signals, %d handlers and %d calls.",
                     cls.__module__, cls.__name__, len(signals),
                     len(nsubs), len(ncalls))

    def register_signal(self, signal, name):
        # not used
        pass


node_bridge = NodeBridge()


class NodeInitMeta(SignalAndHandlerInitMeta.with_external(node_bridge)):
    pass
