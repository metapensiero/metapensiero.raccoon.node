# -*- coding: utf-8 -*-
# :Project:   raccoon.rocky.node -- signal handling utilities
# :Created:   mar 16 feb 2016 16:17:35 CET
# :Author:    Alberto Berti <alberto@metapensiero.it>
# :License:   GNU General Public License version 3 or later
# :Copyright: Copyright (C) 2016, 2017 Arstecnica s.r.l.
#

from abc import ABCMeta, abstractmethod
import asyncio
import inspect
import logging

from autobahn.wamp.types import SubscribeOptions, RegisterOptions
from autobahn.wamp.exception import ApplicationError as WAMPApplicationError
from metapensiero.signal import (ExternalSignallerAndHandler,
                                 SignalAndHandlerInitMeta)

from .registrations import (RegistrationStore, RPCPoint, REG_TYPE_CALL,
                            REG_TYPE_SUB)
from . import serialize


NODE_INTERNAL_SIGNALS = (
    'on_node_bind',
    'on_node_register',
    'on_node_registration_success',
    'on_node_registration_failure',
    'on_node_add',
    'on_node_unbind',
    'on_node_unregister',
)

SPEC_CONTAINER_MEMBER_NAME = '_publish'
"Special attribute name to attach rocky specific info to decorated methods."

logger = logging.getLogger(__name__)


class AbstractWAMPNode(metaclass=ABCMeta):

    @abstractmethod
    def node_register(self):
        pass

    @abstractmethod
    def node_unregister(self):
        pass

    @classmethod
    def __subclasshook__(cls, subcls):
        result = False
        if issubclass(type(subcls), WAMPInitMeta):
            for name in ('on_node_register',  'on_node_registration_success',
                         'on_node_registration_failure', 'on_node_unregister',
                         'node_registered'):
                if not any(name in b.__dict__ for b in subcls.__mro__):
                    break
            else:
                result = True
        return result


def _log(message, *args, **kw):
    from pprint import pformat
    from textwrap import indent

    if args:
        message = message % args
    for name, value in kw.items():
        if value:
            s = indent(pformat(value, width=160), '    ')
            message += '\n  %s:\n%s' % (name, s)
    logger.debug(message)


class NodeWAMPManager:
    """Hooks up into ``metapensiero.signal`` machinery and registers itself
    to handle :term:`WAMP` setup.
    """

    def __init__(self):
        self.reg_store = RegistrationStore(self._dispatch_procedure,
                                           self._dispatch_event)

    def _build_instance_mapping(self, instance, member_names):
        """From a list of class member names, get their bound version."""
        return {name: getattr(instance, mname) for mname,
                name in member_names.items()}

    def _com_guard(self, node):
        """Verify that external communication is possible."""
        if not (node.node_context.wamp_session and
                node.node_context.wamp_session.is_attached()):
            raise RPCError('WAMP session is not initialized properly')

    def _adapt_call_params(self, func, args, kwargs):
        """Adapt the calling parameters to those really requested by ``func``
        signature."""
        signature = inspect.signature(func, follow_wrapped=False)
        has_varkw = any(p.kind == inspect.Parameter.VAR_KEYWORD
                        for n, p in signature.parameters.items())
        if has_varkw:
            bind = signature.bind_partial(*args, **kwargs)
        else:
            bind = signature.bind_partial(
                *args,
                **{k:v for k, v in kwargs.items() if k in
                   signature.parameters})
        bind.apply_defaults()
        return bind.args, bind.kwargs

    def _deserialize(self, node, args, kwargs):
        """Called to deserialize any `Serialized` value."""
        return (tuple((serialize.deserialize(v, node)
                       if isinstance(v, serialize.Serialized) else v)
                      for v in args),
                {k: (serialize.deserialize(v, node) if
                     isinstance(v, serialize.Serialized) else v)
                   for k, v in kwargs.items()})

    def _deserialize_result(self, node, in_result):
        """Deserialize a scalar result or a tuple of results coming from
        :term:`WAMP` calls."""
        if isinstance(in_result, (tuple, list)):
            return type(in_result)(
                (serialize.deserialize(v, node)
                 if isinstance(v, serialize.Serialized) else v)
                for v in in_result)
        else:
            return (serialize.deserialize(in_result, node)
                    if isinstance(in_result, serialize.Serialized) else
                    in_result)

    def _dispatch(self, uri, node, func, wrapper, args, kwargs,
                  local_dispatch=False):
        """This is the dispatch workhorse. All the rpc endpoints will be called using
        this method. It adapts the parameters to those really interesting for the
        function being called.

        :param str uri: the uri (topic or call) for which the endpoint was
          registered
        :param node: the `Node` that registered the endpoint
        :param func: the actual registered endpoint function
        :param wrapper: an optional wrapper for the dispatch defined in the
          node's ``node_context``. If defined, it will be called in place of
          the actual endpoint
        :param args: the parameters to the function
        :param kwargs: the keyword parameters to the function
        :param bool local_dispatch: an optional flag stating if the dispatch
          is local (i.e. called by own `call` or `notify` methods). In souch
          case de/serialization is supposed not to be necessary. Defaults to
          ``False``
        :returns: The result from the wrapper or function call
        """
        if not callable(func):
            raise WAMPApplicationError('The func is missing')
        else:
            try:
                args, kwargs = self._adapt_call_params(func, args, kwargs)
                if not local_dispatch:
                    args, kwargs = self._deserialize(node, args, kwargs)
                if callable(wrapper):
                    result = wrapper(self, uri, node, func, args, kwargs,
                                     local_dispatch=local_dispatch)
                else:
                    result = func(*args, **kwargs)
                if inspect.isawaitable(result):
                    result = self._wrap_async_result(
                        uri, node, result, serialize=not local_dispatch)
                elif not local_dispatch:
                    result = self._serialize_result(node, result)
            except:
                logger.exception("Error while dispatching for '%s'", uri)
                raise
        return result

    def _dispatch_event(self, src_session, src_point, uri, *args,
                        local_dispatch_=False, **kwargs):
        """Dispatch an event to the right endpoint.
        """
        reg_item = self.reg_store.get(uri, REG_TYPE_SUB)
        results = []
        # the case of event dispatchment is a bit more complex than the
        # procedure dispatch, this is because there can be multiple endpoints
        # per session, but they don't get called by autobahn if the source of
        # the event is registered on the same session of the destination.
        for point in reg_item.points:
            # skip destinations registered for sessions different than the
            # reference one, as this method will be called one time per
            # session
            if point.session is not src_session:
                continue
            # skip destination equal to the src_point
            if src_point and point is src_point:
                continue
            wrapper = point.node.node_context.subscription_wrapper
            kw = kwargs.copy()
            if point.is_source:  # it is the signal
                kw.pop('details', None)
            if logger.isEnabledFor(logging.DEBUG):
                _log("Dispatching WAMP event", to=point, uri=uri, args=args,
                     kwargs=kw)
            res = self._dispatch(uri, point.node, point.func, wrapper, args, kw,
                                 local_dispatch=local_dispatch_)
            if res is not None:
                if inspect.isawaitable(res):
                    results.append(res)
        # here the only important thing is to ensure that if a result is a
        # coroutine, it will be properly recognized by the caller and
        # therefore it will wait on it.
        if len(results) == 1:
            return asyncio.ensure_future(results[0])
        elif len(results) > 1:
            return asyncio.gather(*results)

    def _dispatch_procedure(self, src_session, uri, *args,
                            local_dispatch_=False, **kwargs):
        """Dispatch a call from :term:`WAMP` to the right endpoint.
        """
        reg_item = self.reg_store.get(uri, REG_TYPE_CALL)
        assert len(reg_item) == 1  # procedure registrations cannot have more
                                   # than one endpoint
        point = tuple(reg_item.points)[0]
        wrapper = point.node.node_context.call_wrapper
        if logger.isEnabledFor(logging.DEBUG):
            _log("Dispatching WAMP call", uri=uri, args=args, kwargs=kwargs)
        return self._dispatch(
            uri, point.node, point.func, wrapper, args, kwargs,
            local_dispatch=local_dispatch_)

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
                await self.reg_store.add_call(node, context, *uri_endpoints)
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

                points = await self.reg_store.add_subscription(node, context,
                                                               *sig_endpoints)
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
                await self.reg_store.add_subscription(node, context,
                                                      *sub_endpoints)
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

    def _serialize(self, node, args, kwargs):
        """Called to serialize any serializable value."""
        return (tuple((serialize.serialize(v, node) if
                       isinstance(v, serialize.Serializable) else v)
                      for v  in args),
                {k: (serialize.serialize(v, node) if
                     isinstance(v, serialize.Serializable) else v)
                   for k, v in kwargs.items()})

    def _serialize_result(self, node, in_result):
        """Deserialize a scalar result or a tuple of results coming from
        :term:`WAMP` calls when """
        if isinstance(in_result, (tuple, list)):
            return type(in_result)(
                (serialize.serialize(v, node) if
                 isinstance(v, serialize.Serializable) else v)
                for v in in_result)
        else:
            return (serialize.serialize(in_result, node)
                    if isinstance(in_result, serialize.Serializable) else
                    in_result)

    async def _wrap_async(self, data):
        return data

    async def _wrap_async_result(self, uri, node, in_result, *,
                                 serialize=False, deserialize=False):
        """Called by `_dispatch`. Wrap an async result to catch and log possible
        exceptions and to serialize or deserialize it if necessary.

        """
        try:
            in_result = await in_result
        except:
            logger.exception("Error while dispatching for '%s'", uri)
            raise
        if serialize:
            return self._serialize_result(node, in_result)
        elif deserialize:
            return self._deserialize_result(node, in_result)
        else:
            return in_result

    def call(self, node, path, *args, **kwargs):
        """Call another RPC endpoint published via :term:`WAMP`.

        .. important::
          The ``disclose_me=True`` option (was the default in old
          ``raccoon.api`` framework) is now managed directly by
          crossbar in its realm/role configuration.

        .. note::
          this isn't a coroutine but it returns one.
        """
        self._com_guard(node)
        if isinstance(path, str):
            path = node.node_path.resolve(path, node.node_context)
        str_path = str(path)
        session = node.node_context.wamp_session
        item = self.reg_store.get(str_path, REG_TYPE_CALL)
        if len(item) > 0 and session in item.regs:
            local_dispatch = True
            details = {'procedure': str_path, 'caller': 'local'}
            result = self._dispatch_procedure(
                session, str_path, *args, details=details,
                local_dispatch_=True, **kwargs)
        else:
            local_dispatch = False
            args, kwargs = self._serialize(node, args, kwargs)
            try:
                result = node.node_context.wamp_session.call(
                    str_path, *args, **kwargs)
            except:
                logger.exception("Error while dispatching to '%s'", str_path)
                raise
        if inspect.isawaitable(result):
            if not local_dispatch:
                result = self._wrap_async_result(str_path, node, result,
                                                 deserialize=True)
        else:
            if not local_dispatch:
                result = self._deserialize_result(node, result)
            result = self._wrap_async(result)
        return result

    def clear(self):
        self.reg_store.clear()

    async def connect(self, node, path, handler):
        """Emulate signal api to connect an handler to a subscription."""
        self._com_guard(node)
        if isinstance(path, str):
            path = node.node_path.resolve(path, node.node_context)
        try:
            await self.reg_store.add_subscription(node, node.node_context,
                                                  (str(path), handler, False))
        except WAMPApplicationError:
            logger.exception("Error while registering subscription to '%s'",
                             path)
            raise

    async def disconnect(self, node, path, handler):
        """Emulate signal api to disconnect an handler from a subscription."""
        self._com_guard(node)
        if isinstance(path, str):
            path = node.node_path.resolve(path, node.node_context)
        try:
            await self.reg_store.remove(node, node.node_context, str(path),
                                        handler, REG_TYPE_SUB)
        except WAMPApplicationError:
            logger.exception("Error while unregistering subscription to '%s'",
                             path)
            raise

    def get_point(self, node, func=None):
        return RPCPoint(node, func)

    def notify(self, src_point, path, *args, awaitable=False, **kwargs):
        r"""Execute a notification on the signal at `path`. This takes care of
        executing local dispatching for the sessions controlled by this
        manager, if any. `src_point` can be an instance of EndpointDef to
        exclude from the notification. This is only used by
        :meth:`publish_signal` later on to avoid circular signalling.

        Differently by the `metapensiero.signal.Signal` API, this is more in
        line with the autobahn's ``Session.publish()`` API in that the
        notification is something that is inherently disconnected from its
        side effects. For this reason by default this method returns ``None``.

        :param src_point: an instance of `registrations.RPCPoint` initialized
          with informations about the source `Node`
        :param path: the *signal* or *topic* to notify. This can be a string
          or a `Path` instance
        :param \*args: the positional arguments to send
        :param awaitable: a flag that that will change the return value into
          an *awaitable*. It will use the awaitable returned by the (local)
          notification if possible, or a faked coroutine that just wraps
          ``None``
        :params \*\*kwargs: the keyword arguments to send
        :returns: ``None`` or an awaitable
        """
        self._com_guard(src_point.node)
        if isinstance(path, str):
            path = src_point.node.node_path.resolve(
                path, src_point.node.node_context)
        str_path = str(path)
        item = self.reg_store.get(str_path, REG_TYPE_SUB)
        session = src_point.node.node_context.wamp_session
        if logger.isEnabledFor(logging.DEBUG):
            _log("Publishing to WAMP", path=str_path, args=args, kwargs=kwargs)
        if len(item) > 0 and session in item.regs:
            details = {'topic': str_path, 'publisher': 'local'}
            disp = self._dispatch_event(session, src_point, str_path, *args,
                                        details=details, local_dispatch_=True,
                                        **kwargs)
        else:
            disp = None
        wrapper = src_point.node.node_context.publication_wrapper
        args, kwargs = self._serialize(src_point.node, args, kwargs)
        if callable(wrapper):
            # TODO: check all wrappers api
            publication = wrapper(self, src_point, str_path, args, kwargs)
        else:
            publication = session.publish(str_path, *args, **kwargs)

        coros = []
        for res in (disp, publication):
            if inspect.isawaitable(res):
                coros.append(res)
        if len(coros) == 1:
            # the calling context is expected not to wait on this, hence the
            # ensure_future to be certain that the coro will be scheduled
            res = asyncio.ensure_future(coros[0])
            if not awaitable:
                res = None
        elif len(coros) > 1:
            # this has to run no matter way, because it ensures correct
            # scheduling
            res = asyncio.gather(*coros, loop=src_point.node.node_context.loop)
            if not awaitable:
                res = None
        else:
            if awaitable:
                res = self._wrap_async(None)
            else:
                res = None
        return res

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
        return self.notify(src_point, wamp_topic, *args, **ext_kwargs)

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
            logger.warning("Not registering class %s.%s as it doesn't implement"
                           " AbstractWAMPNode", cls.__module__, cls.__name__)
        cls._wamp_subscriptions = wsubs
        cls._wamp_calls = wcalls
        logger.debug("Scanned class %s.%s for WAMP points, found "
                     "%d signals, %d subscriptions and %d calls ",
                     cls.__module__, cls.__name__, len(signals),
                     len(wsubs), len(wcalls))

    def register_signal(self, signal, name):
        # not used
        pass


ExternalSignallerAndHandler.register(NodeWAMPManager)

node_wamp_manager = NodeWAMPManager()


class WAMPInitMeta(SignalAndHandlerInitMeta.with_external(node_wamp_manager)):

    @property
    def manager(self):
        return self._external_signaller_and_handler


class RPCError(Exception):
    "Exception raised when an RPC cannot be performed."


class CallDecoMeta(type):
    """A metaclass to deal with the double protocol of decorators about
    their definition.
    """

    def __call__(cls, method_or_name=None):
        if method_or_name is None or isinstance(method_or_name, str):
            res = super().__call__(method_or_name)
        else:
            res = super().__call__()(method_or_name)
        return res


class CallNameDecorator(metaclass=CallDecoMeta):
    "A decorator used to mark a method as a call."

    def __init__(self, call_name=None):
        self.call_name = call_name
        if call_name and '.' in call_name and len(call_name) > 1:
            raise RPCError('Call names cannot contain dots')

    def __call__(self, method):
        setattr(method, SPEC_CONTAINER_MEMBER_NAME,
                {'kind': 'call', 'name': self.call_name})
        return method

    @classmethod
    def is_call(cls, name, value):
        """Detect an a call and return its wanted name."""
        call_name = False
        if callable(value) and hasattr(value, SPEC_CONTAINER_MEMBER_NAME):
                spec = getattr(value, SPEC_CONTAINER_MEMBER_NAME)
                if spec['kind'] == 'call':
                    call_name = spec['name']
        return call_name


call = CallNameDecorator
