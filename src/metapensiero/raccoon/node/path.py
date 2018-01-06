# -*- coding: utf-8 -*-
# :Project:   metapensiero.raccoon.node -- path resolution utility
# :Created:   mar 16 feb 2016 19:46:39 CET
# :Author:    Alberto Berti <alberto@metapensiero.it>
# :License:   GNU General Public License version 3 or later
# :Copyright: © 2016, 2017, 2018 Alberto Berti
#

from collections import abc
import re
from weakref import WeakValueDictionary

from . import serialize


PATHSEP = '.'
INVALID_URI_CHARS = re.compile('[^a-z0-9._*]', flags=re.ASCII)


def norm_path(value, full=False):
    """Return a normalized tuple of the value. If the value is a `Path` it
    returns the possible relative path from the base or an absolute if
    ``full`` is ``True``.
    """
    if isinstance(value, Path):
        normalized = value._path
        if value.base is not None and full:
            normalized = value.base._path + normalized
    else:
        if isinstance(value, abc.Sequence):
            if isinstance(value, str):
                value = value.split(PATHSEP)
            if not isinstance(value, tuple):
                value = tuple(value)
        elif isinstance(value, abc.Iterable):
            value = tuple(value)
        else:
            raise ValueError("Invalid value {value!r}".format(value=value))
        normalized = value
    if len(normalized) == 0:
        raise ValueError("Empty value")
    return normalized


class PathError(Exception):
    """Error raised during path operations"""


class PathMeta(type(serialize.Serializable)):

    REGISTRY = WeakValueDictionary()

    def __call__(cls, path, base=None):
        reg = cls.REGISTRY
        # normalization
        if not path:
            raise PathError("'path' must have a value")
        elif isinstance(path, cls) and not base:
            assert ((path._path, base) in reg and reg[(path._path, base)] is
                    path), ("Path instance is not registered for path "
                            "{!r}".format(path))
            return path
        elif isinstance(path, cls) and base:
            raise PathError("Cannot be both Path instances")
        else:
            path = norm_path(path)
        base = norm_path(base) if base else None
        exists = reg.get((path, base))
        if exists:
            result = exists
        else:
            result = super().__call__(path, base)
            reg[(path, base)] = result
        return result


@serialize.define('raccoon.node.Path')
class Path(serialize.Serializable, metaclass=PathMeta):
    """Helper used to resolve call, subscribe and publish paths.

    :param path: either a *dotted* string or a tuple of fragments
    :param base: optional base path, same spec

    This helps especially when dealing with a notion of a *base* path and a
    *relative* one to it.
    """

    base = None

    def __init__(self, path,  base=None):
        self._path = norm_path(path)
        if base and not isinstance(base, Path):
            base = Path(base)
        self.base = base

    def __add__(self, other):
        """Add a path with a string or tuple or two Path instances.

        :param other: either a dotted string or a tuple or an instance
          of this same class
        :returns: an instance of this class
        """
        if not isinstance(other, Path):
            if self.base is self:
                path = norm_path(other)
            else:
                path = self._path + norm_path(other)
            base = self.base
        else:
            bases = {self.base, other.base}
            if None in bases:
                if self.base is self:
                    path = other._path
                else:
                    path = self._path + other._path
                if len(bases) == 2:
                    base = self.base or other.base
                else:
                    base = None
            else:
                raise PathError("Cannot add two paths with a base path")
        return type(self)(path, base)

    def __eq__(self, other):
        return norm_path(other, full=True) == norm_path(self, full=True)

    __getattr__ = __add__

    def __getitem__(self, index):
        return self.path[index]

    def __hash__(self):
        return hash(norm_path(self, full=True))

    def __len__(self):
        return len(self.path)

    def __repr__(self):
        return "<%s.%s for '%s'>" % (
            type(self).__module__,
            type(self).__name__,
            str(self)
        )

    def __str__(self):
        return PATHSEP.join(self.path)

    @property
    def absolute(self):
        return type(self)(self.path)

    @classmethod
    def node_deserialize(cls, value, endpoint_node):
        return cls(**value)

    @classmethod
    def node_serialize(cls, instance, srcpoint_node):
        return {'path': instance._path,
                'base': instance.base.path if instance.base is not None else None}

    @property
    def path(self):
        """The absolute path, maybe the composition of the base path with the
        *local* one."""
        if self.base is not None and self.base is not self:
            result = self.base.path + self._path
        else:
            result = self._path
        return result

    def resolve(self, path, context=None):
        """Resolve a potentially relative path into an absolute path.

        :param path: either a *dotted* string or a sequence of path fragments
        :returns: an instance of this class

        If the path is already absolute it will be returned as-is.  A relative
        address is marked by an initial '@', the rest of the address will be
        added to the session path.
        """
        if isinstance(path, Path):
            raise PathError("The path to resolve cannot be a Path instance")
        path = list(norm_path(path))
        out_path = None
        if path[0].startswith('@'):
            if not self.base:
                raise PathError("Cannot do base resolution if the path "
                                "hasn't one.")
            path[0] = path[0][1:]
            if not path[0]:
                path.pop(0)
            out_path = self.base.path + tuple(path)
        if not out_path and context:
            path_resolvers = context.get('path_resolvers')
            if path_resolvers:
                path = tuple(path)
                for resolver in path_resolvers:
                    out_path = resolver(self, path, context)
                    if out_path:
                        break
        if out_path:
            res = type(self)(out_path)
        elif not out_path and INVALID_URI_CHARS.search(PATHSEP.join(path)):
            raise PathError("Failed resolution of path '%s'" %
                            PATHSEP.join(path))
        else:
            res = type(self)(path)
        return res
