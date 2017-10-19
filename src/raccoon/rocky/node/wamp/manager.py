# -*- coding: utf-8 -*-
# :Project:   raccoon.rocky.node --- machinery to register calls and events
#             with WAMP
# :Created:   mer 18 ott 2017 19:51:50 CEST
# :Author:    Alberto Berti <alberto@metapensiero.it>
# :License:   GNU General Public License version 3 or later
# :Copyright: Copyright © 2016, 2017 Arstecnica s.r.l.
#

import asyncio
import inspect
import logging

from autobahn.wamp.exception import ApplicationError as WAMPApplicationError

from ..registrations import RPCPoint, RegistrationType
from ..serialize import (deserialize_args, deserialize_result, serialize_args,
                        serialize_result)

from .errors import RPCError
from . import log_noisy_error


logger = logging.getLogger(__name__)


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
    """Does the hard work of dispatching calls and event to the `WAMP`:term:
    world."""

    def __init__(self, reg_store):
        self.reg_store = reg_store

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

    def dispatch(self, uri, node, func, wrapper, args, kwargs,
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
                    args, kwargs = deserialize_args(args, kwargs, node)
                if callable(wrapper):
                    result = wrapper(self, uri, node, func, args, kwargs,
                                     local_dispatch=local_dispatch)
                else:
                    result = func(*args, **kwargs)
                if inspect.isawaitable(result):
                    result = self._wrap_async_result(
                        uri, node, result, serialize=not local_dispatch)
                elif not local_dispatch:
                    result = serialize_result(result, node)
            except:
                log_noisy_error(logger, "Error while dispatching for '%s'", uri)
                raise
        return result

    def dispatch_event(self, src_session, src_point, uri, *args,
                       local_dispatch_=False, **kwargs):
        """Dispatch an event to the right endpoint.
        """
        reg_item = self.reg_store.get(uri, RegistrationType.SUB)
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
            res = self.dispatch(uri, point.node, point.func, wrapper, args, kw,
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

    def dispatch_procedure(self, src_session, uri, *args,
                           local_dispatch_=False, **kwargs):
        """Dispatch a call from :term:`WAMP` to the right endpoint.
        """
        reg_item = self.reg_store.get(uri, RegistrationType.CALL)
        assert len(reg_item) == 1  # procedure registrations cannot have more
                                   # than one endpoint
        point = tuple(reg_item.points)[0]
        wrapper = point.node.node_context.call_wrapper
        if logger.isEnabledFor(logging.DEBUG):
            _log("Dispatching WAMP call", uri=uri, args=args, kwargs=kwargs)
        return self.dispatch(
            uri, point.node, point.func, wrapper, args, kwargs,
            local_dispatch=local_dispatch_)

    async def _wrap_async(self, data):
        return data

    async def _wrap_async_result(self, uri, node, in_result, *,
                                 serialize=False, deserialize=False):
        """Called by `dispatch`. Wrap an async result to catch and log possible
        exceptions and to serialize or deserialize it if necessary.

        """
        try:
            in_result = await in_result
        except:
            log_noisy_error(logger, "Error while dispatching for '%s'", uri)
            raise
        if serialize:
            return serialize_result(in_result, node)
        elif deserialize:
            return deserialize_result(in_result, node)
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
        item = self.reg_store.get(str_path, RegistrationType.CALL)
        if len(item) > 0 and session in item.regs:
            local_dispatch = True
            details = {'procedure': str_path, 'caller': 'local'}
            result = self.dispatch_procedure(
                session, str_path, *args, details=details,
                local_dispatch_=True, **kwargs)
        else:
            local_dispatch = False
            args, kwargs = serialize_args(args, kwargs, node)
            try:
                result = node.node_context.wamp_session.call(
                    str_path, *args, **kwargs)
            except:
                log_noisy_error(logger, "Error while dispatching to '%s'",
                                str_path)
                raise
        if inspect.isawaitable(result):
            if not local_dispatch:
                result = self._wrap_async_result(str_path, node, result,
                                                 deserialize=True)
        else:
            if not local_dispatch:
                result = deserialize_result(result, node)
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
            log_noisy_error(logger, "Error while registering subscription to "
                            "'%s'", path)
            raise

    async def disconnect(self, node, path, handler):
        """Emulate signal api to disconnect an handler from a subscription."""
        self._com_guard(node)
        if isinstance(path, str):
            path = node.node_path.resolve(path, node.node_context)
        try:
            await self.reg_store.remove(node, node.node_context, str(path),
                                        handler, RegistrationType.SUB)
        except WAMPApplicationError:
            log_noisy_error(logger, "Error while unregistering subscription to "
                            "'%s'", path)
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
        item = self.reg_store.get(str_path, RegistrationType.SUB)
        session = src_point.node.node_context.wamp_session
        if logger.isEnabledFor(logging.DEBUG):
            _log("Publishing to WAMP", path=str_path, args=args, kwargs=kwargs)
        if len(item) > 0 and session in item.regs:
            details = {'topic': str_path, 'publisher': 'local'}
            disp = self.dispatch_event(session, src_point, str_path, *args,
                                       details=details, local_dispatch_=True,
                                       **kwargs)
        else:
            disp = None
        wrapper = src_point.node.node_context.publication_wrapper
        args, kwargs = serialize_args(args, kwargs, src_point.node)
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
