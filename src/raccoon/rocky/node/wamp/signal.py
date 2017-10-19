# -*- coding: utf-8 -*-
# :Project:   raccoon.rocky.node -- metapensiero.signal hookup
# :Created:   mer 18 ott 2017 19:51:50 CEST
# :Author:    Alberto Berti <alberto@metapensiero.it>
# :License:   GNU General Public License version 3 or later
# :Copyright: Copyright © 2016, 2017 Arstecnica s.r.l.
#

import logging

from autobahn.wamp.exception import ApplicationError as WAMPApplicationError
from autobahn.wamp.types import SubscribeOptions, RegisterOptions
from metapensiero.signal import (ExternalSignallerAndHandler,
                                 SignalAndHandlerInitMeta)

from ..registrations import RegistrationStore

from .abc import AbstractWAMPNode
from .deco import CallNameDecorator
from .manager import NodeWAMPManager
from . import NODE_INTERNAL_SIGNALS


logger = logging.getLogger(__name__)


class WAMPBridge(ExternalSignallerAndHandler):
    """Hooks up into ``metapensiero.signal`` machinery and registers itself
    to handle :term:`WAMP` setup.
    """

    def __init__(self):
        self.reg_store = RegistrationStore()
        self.manager = NodeWAMPManager(self.reg_store)

    def _build_instance_mapping(self, instance, member_names):
        """From a list of class member names, get their bound version."""
        return {name: getattr(instance, mname) for mname,
                name in member_names.items()}

    async def _on_node_register(self, node, context):
        """It's an handler registered at class registration time. It works on
        a single node and registers marked event handlers and procedures with
        :term:`WAMP`.

        This is the second step of the registration of a node object and
        happens on every instance.
        """
        path = str(node.node_path)
        session = context.wamp_session
        assert session.is_attached()
        call_reg_opts = context.call_registration_options or \
                        RegisterOptions()
        call_reg_opts.details_arg = 'details'
        sub_reg_opts = context.subscription_registration_options or \
                       SubscribeOptions()
        sub_reg_opts.details_arg = 'details'
        calls_data = type(node)._wamp_calls
        subs_data = type(node)._wamp_subscriptions

        signals_data = type(node)._signals
        # filter out internal signals
        signals_data = {n: sig for n, sig in signals_data.items() if
                        (n not in NODE_INTERNAL_SIGNALS) and sig is not None}
        path = node.node_path
        logger.debug("Beginning registration of: %s", node)
        # deal with calls first
        if len(calls_data) > 0:
            try:
                # build a mapping of (name, bound method) for the calls data
                # on this node
                call_endpoints = self._build_instance_mapping(node, calls_data)
                uri_endpoints = []
                for name, func in call_endpoints.items():
                    if name == '.':
                        p = path.path
                    else:
                        p = path.path + (name,)
                    uri_endpoints.append(('.'.join(p), func))
                await self.reg_store.add_call(
                    node, context, self.manager.dispatch_procedure,
                    *uri_endpoints)
            except WAMPApplicationError:
                logger.exception("Error while registering procedures")
                await node.on_node_registration_failure.notify(node=node,
                                                               context=context)
                raise

        # deal with signals
        if len(signals_data) > 0:
            try:
                sig_endpoints = []
                iproxies = []
                for name, sig in signals_data.items():
                    if name == '.':
                        p = path.path
                    else:
                        p = path.path + (name,)
                    iproxy = sig.__get__(node)
                    iproxies.append(iproxy)
                    sig_endpoints.append(('.'.join(p),
                                          iproxy.notify_no_ext, True))

                points = await self.reg_store.add_subscription(
                    node, context, self.manager.dispatch_event, *sig_endpoints)
                for p, ip in zip(points, iproxies):
                    ip.wamp_point = p
            except WAMPApplicationError:
                logger.exception("Error while registering signals")
                await node.on_node_registration_failure.notify(node=node,
                                                               context=context)
                raise

        # deal with subscriptions
        if len(subs_data) > 0:
            try:
                raw_endpoints = self._build_instance_mapping(node, subs_data)
                sub_endpoints = []
                for name, func in raw_endpoints.items():
                    if name == '.':
                        p = str(path)
                    else:
                        p = str(path.resolve(name, context))
                    sub_endpoints.append((p, func, False))
                await self.reg_store.add_subscription(
                    node, context, self.manager.dispatch_event, *sub_endpoints)
            except WAMPApplicationError:
                logger.exception("Error while registering subscriptions")
                await node.on_node_registration_failure.notify(node=node,
                                                               context=context)
                raise
        node.node_registered = True
        await node.on_node_registration_success.notify(node=node,
                                                       context=context)
        logger.debug("Completed registration of: %s", node)

    async def _on_node_unregister(self, node, context):
        """Unregister event handlers and calls from :term:`WAMP`."""
        assert context.wamp_session.is_attached()
        logger.debug("Beginning unregistration of: %s", node)
        try:
            await self.reg_store.remove(node, context)
        except WAMPApplicationError:
            logger.exception("An error occurred during unregistration of: %s",
                             node)
        logger.debug("Completed unregistration of: %s", node)

    def publish_signal(self, signal, instance, loop, args, kwargs):
        """Signal API. Publish a signal via :term:`WAMP`. The topic is the
        node's path + the signal name.

        .. important::
          The ``disclose_me=True`` option (was the default in old
          ``raccoon.api`` framework) is now managed directly by
          crossbar in it's realm/role configuration.

        If the ``node_context.publication_wrapper`` is defined and
        callable, it will delegate all the publication operation to
        it.

        The return value can be a coroutine because the Signal
        instance that calls into this will add it to the current
        transaction, if any.
        """
        sname = signal.name
        if sname in NODE_INTERNAL_SIGNALS or not instance.node_registered:
            return
        if sname == '.':
            wamp_topic = instance.node_path
        else:
            wamp_topic = instance.node_path + sname
        # mangle kwargs to expunge those to begin with 'local_', this
        # way the notifier can still add non JSON-encodable object as
        # params while being sure that this will not cause an error
        # during WAMP publication
        ext_kwargs = {k: v for k, v in kwargs.items()
                      if not k.startswith('local_')}
        src_point = signal.__get__(instance).wamp_point
        return self.manager.notify(src_point, wamp_topic, *args, **ext_kwargs)

    def register_class(self, cls, bases, namespace, signals, handlers):
        """Signal API. This is called by SignalAndHandlerInitMeta.

        It finds :term:`WAMP` (event) handlers and :term:`WAMP` calls
        defined in the bodies of this class bases using utilities
        provided by the SignalAndHandlerInitMeta class.

        Then filters the handlers in namespace to find those who don't
        refer to the signals defined in the class and adds them as
        :term:`WAMP` subscriptions.

        Then finds namespace's calls and add them too as :term:`WAMP`
        class.

        Then connects ``register`` and ``unregister`` signals to to
        this instance handlers.

        Finally saves all the data on the class.
        """
        wsubs, wcalls = cls._build_inheritance_chain(
            bases, '_wamp_subscriptions', '_wamp_calls', merge=True)

        # find calls
        for aname, avalue in namespace.items():
            call_name = CallNameDecorator.is_call(aname, avalue)
            if call_name:
                wcalls[aname] = call_name
            elif call_name is None:
                wcalls[aname] = aname

        # connect to signals
        # class is constructed already
        if issubclass(cls, AbstractWAMPNode):
            # filter handlers
            new_wsubs = {}
            for hname, sig_name in handlers.items():
                if sig_name not in signals:
                    new_wsubs[hname] = sig_name
            for hname in new_wsubs.keys():
                del handlers[hname]
            wsubs.update(new_wsubs)
            cls.on_node_register.connect(self._on_node_register)
            cls.on_node_unregister.connect(self._on_node_unregister)
        else:
            logger.warning("Not registering class %s.%s as it doesn't "
                           " implement AbstractWAMPNode", cls.__module__,
                           cls.__name__)
        cls._wamp_subscriptions = wsubs
        cls._wamp_calls = wcalls
        logger.debug("Scanned class %s.%s for WAMP points, found "
                     "%d signals, %d subscriptions and %d calls ",
                     cls.__module__, cls.__name__, len(signals),
                     len(wsubs), len(wcalls))

    def register_signal(self, signal, name):
        # not used
        pass


wamp_bridge = WAMPBridge()


class WAMPInitMeta(SignalAndHandlerInitMeta.with_external(wamp_bridge)):

    @property
    def manager(self):
        return self._external_signaller_and_handler.manager
