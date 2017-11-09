# -*- coding: utf-8 -*-
# :Project:   raccoon.rocky.node -- single rpc endpoint class
# :Created:   gio 26 ott 2017 16:18:28 CEST
# :Author:    Alberto Berti <alberto@metapensiero.it>
# :License:   GNU General Public License version 3 or later
# :Copyright: Copyright © 2017 Arstecnica s.r.l.
#

import inspect
from abc import ABCMeta, abstractproperty
from collections import namedtuple
from weakref import WeakValueDictionary

from metapensiero.signal.core import InstanceProxy, Signal


from .. import NoResult
from .errors import RPCError
from .utils import RPCType


class PointKeyMeta(ABCMeta):
    """An abstract base class for a namedtuple like type"""

    def __new__(mcls, name, bases, namespace):
        added_fields = namespace.get('_added_fields')
        for base in bases:
            if added_fields is not None:
                break
            added_fields = getattr(base, '_added_fields', None)
        fields = None
        for base in bases:
            if fields is not None:
                break
            fields = getattr(base, '_fields', None)
        if not isinstance(added_fields, abstractproperty):
            if isinstance(added_fields, str):
                added_fields = tuple(added_fields.split())
            if isinstance(fields, str):
                fields = tuple(fields.split())
            basetuple = namedtuple(name + 'NamedTuple', fields + added_fields)
            bases = (basetuple,) + bases
            namespace.pop('_fields', None)
            namespace.setdefault('__doc__', AbstractPointKey.__doc__)
            namespace.setdefault('__slots__', ())
        return ABCMeta.__new__(mcls, name, bases, namespace)


class AbstractPointKey(metaclass=PointKeyMeta):
    """A tuple-like object containing key and indexing information for
    points."""

    _fields = ('owner',)
    _added_fields = abstractproperty()


class OwnerKey(AbstractPointKey):

    _added_fields = ()

    def point(self, *args, **kwargs):
        return EndPoint(self, *args, *kwargs)


class PointMeta(type):

    all = WeakValueDictionary()

    key_point_map = {}

    def __new__(mcls, name, bases, namespace):
        key_cls = namespace.get('KEY_CLS', None)
        if key_cls is None:
            raise TypeError("Missing 'KEY_CLS' in body")
        assert issubclass(key_cls, OwnerKey)
        assert key_cls not in mcls.key_point_map
        cls = type.__new__(mcls, name, bases, namespace)
        mcls.key_point_map[key_cls] = cls
        return cls

    def __call__(cls, key, **opts):
        assert isinstance(key, OwnerKey)
        assert type(key) in cls.key_point_map
        if key in cls.all:
            res = cls.all[key]
        else:
            if cls is EndPoint:
                real_cls = cls.key_point_map[type(key)]
            else:
                real_cls = cls
            res = type.__call__(real_cls, key, **opts)
            cls.all[key] = res
        return res

    def key_for(cls, *args, **kwargs):
        """Calculate the key for the (owner, path) pair.

        :param owner: an object that owns the endpoint
        :param path: the path associated, if any
        :returns: an hashable object to be used as key
        """
        return cls.KEY_CLS(*args, **kwargs)


class EndPoint(metaclass=PointMeta):
    """Information about a single end point of an RPC. Every service or entity
    that wants to join the dispatching for a path must add a specific point
    to the registry. Point are associated one to one with a declared key.

    :keyword bool is_source: whether the point is a *source* or an *end* point
    """

    KEY_CLS = OwnerKey
    active = False
    key = None
    is_source = False
    remote = False
    managed = False

    def __init__(self, key):
        self.key = key
        self.rpc_records = set()

    def __eq__(self, other):
        return (isinstance(other, EndPoint) and
                hash(self.key) == hash(other.key))

    def __hash__(self):
        return self.key.__hash__()

    def __repr__(self):
        return ("<%s for owner %r is source: %r>" % (
            self.__class__.__name__, self.owner, self.is_source
        ))

    def _adapt_call_params(self, func, args, kwargs):
        signature = inspect.signature(func, follow_wrapped=False)
        has_varkw = any(p.kind == inspect.Parameter.VAR_KEYWORD
                        for n, p in signature.parameters.items())
        if has_varkw:
            bind = signature.bind_partial(*args, **kwargs)
        else:
            bind = signature.bind_partial(*args,
                                          **{k: v for k, v in kwargs.items()
                                             if k in signature.parameters})
            bind.apply_defaults()
        return bind

    def attach(self, rpc_record):
        """Attach to the rpc record"""
        if rpc_record in self.rpc_records:
            raise RPCError("Already attached")
        rpc_record.add(self)
        self.active = True
        return self

    def detach(self, rpc_record):
        """Detach from rpc_record"""
        rpc_record.remove(self)
        self.active = False
        return self

    def call(self, *args, **kwargs):
        return NoResult

    @property
    def is_attached(self):
        return len(self.rpc_records) > 0

    @property
    def owner(self):
        return self.key.owner


class TypedKey(OwnerKey):
    _added_fields = ('rpc_type')

    def __new__(cls, owner, rpc_type):
        cls._validate_rpc_type(rpc_type)
        return super().__new__(cls, owner, rpc_type)

    @classmethod
    def _validate_rpc_type(cls, rpc_type):
        if not isinstance(rpc_type, RPCType):
            raise RPCError("'rpc_type' must be one of RPCType, got "
                           "{!r}".format(rpc_type))


class TypedPoint(EndPoint):

    KEY_CLS = TypedKey

    def __init__(self, key):
        if not isinstance(key, TypedKey):
            raise RPCError("Invalid key type %r" % key)
        super().__init__(key)

    @property
    def rpc_type(self):
        return self.key.rpc_type




class SignalKey(TypedKey):
    """A key for a signal endpoint."""

    _added_fields = ('signal',)

    def __new__(cls, owner, signal):
        if isinstance(signal, InstanceProxy):
            signal = signal.signal
        elif not isinstance(signal, Signal):
            raise ValueError("'signal' must be an Signal, "
                             "got {!r}".format(signal))
        return super().__new__(cls, owner, RPCType.EVENT, signal)


class SignalPoint(TypedPoint):

    KEY_CLS = SignalKey
    is_source = True


    def __repr__(self):
        return ("<%s for owner %r and signal %r, is source: %r>" % (
            self.__class__.__name__, self.owner, self.signal, self.is_source
        ))

    @property
    def signal(self):
        return self.key.signal

    @property
    def instance(self):
        return self.key.owner

    @property
    def proxy(self):
        return self.signal.__get__(self.instance)

    def call(self, *args, **kwargs):
        return self.proxy.notify_prepared(args, kwargs,
                                          notify_external=False)


class HandlerKey(TypedKey):
    """A key for defining handlers points."""

    _added_fields = ('func', 'self')

    @classmethod
    def _decompose_method(cls, func_or_method):
        if inspect.ismethod(func_or_method):
            fself = func_or_method.__self__
            func_or_method = func_or_method.__func__
        else:
            fself = None
        return func_or_method, fself

    def __new__(cls, owner, func_or_method):
        func_or_method, fself = cls._decompose_method(func_or_method)
        return super().__new__(cls, owner, RPCType.EVENT, func_or_method,
                               fself)


class HandlerPoint(TypedPoint):
    """A specific point for handlers."""

    KEY_CLS = HandlerKey

    def __repr__(self):
        return ("<%s for owner %r and handler (%r, %r), is source: %r>" % (
            self.__class__.__name__, self.owner, self.fself, self.func,
            self.is_source
        ))

    def call(self, *args, **kwargs):
        if self.fself is not None:
            args = (self.fself,) + args
        bind = self._adapt_call_params(self.func, args, kwargs)
        return self.func(*bind.args, **bind.kwargs)

    @property
    def func(self):
        return self.key.func

    @property
    def fself(self):
        return self.key.self


class CallKey(HandlerKey):

    _added_fields = ()

    def __new__(cls, owner, func_or_method):
        func_or_method, fself = cls._decompose_method(func_or_method)
        return super().__new__(cls, owner, RPCType.CALL, func_or_method,
                               fself)


class CallPoint(HandlerPoint):
    """A specific point for calls."""

    KEY_CLS = CallKey

    def attach(self, rpc_record):
        """Attach to an rpc_record"""
        if len(rpc_record[RPCType.CALL]) > 0:
            raise RPCError("Duplicate call endpoint for "
                           "path {!r}".format(rpc_record.path))
        else:
            return super().attach(rpc_record)
