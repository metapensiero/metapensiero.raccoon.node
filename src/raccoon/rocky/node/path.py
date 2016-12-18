# -*- coding: utf-8 -*-
# :Project:   raccoon.rocky.node -- path resolution utility
# :Created:   mar 16 feb 2016 19:46:39 CET
# :Author:    Alberto Berti <alberto@metapensiero.it>
# :License:   GNU General Public License version 3 or later
# :Copyright: Copyright (C) 2016 Arstecnica s.r.l.
#

from collections import abc
from weakref import WeakValueDictionary

PATHSEP = '.'


def norm_path(value):
    if isinstance(value, Path):
        value = value._path
    else:
        if isinstance(value, abc.Sequence) and isinstance(value, str):
            value = value.split(PATHSEP)
        if not isinstance(value, tuple):
            value = tuple(value)
    return value


class PathError(Exception):
    """Error raised during path operations"""


class PathMeta(type):

    REGISTRY = WeakValueDictionary()

    def __call__(cls, path, base=None):
        reg = cls.REGISTRY
        # normalization
        if not path:
            raise PathError("'path' must have a value")
        elif isinstance(path, cls) and not base:
            reg[(path._path, base)] = path
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
        return result


class Path(metaclass=PathMeta):
    """Helper used to resolve call, subscribe and publish paths.

    This helps especially dealing with a notion of a *base* path and a
    *relative* one to it.
    """

    def __init__(self, path,  base=None):
        """:param path: either a *dotted* string or a tuple of fragments
        :param base: optional base path, same spec
        """
        self._path = norm_path(path)
        if base and not isinstance(base, Path):
            base = Path(base)
        self.base = base

    @property
    def path(self):
        """The absolute path, maybe the composition of the base path with the
        'local' one."""
        if self.base is not None and self.base is not self:
            result = self.base.path + self._path
        else:
            result = self._path
        return result

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
                raise PathError("Cannot add two path with a base path")
        return type(self)(path, base)

    __getattr__ = __add__

    def __getitem__(self, index):
        return self.path[index]

    def resolve(self, path):
        """Resolve a potentially relative path into an absolute path.

        :param value: either a *dotted* string or a sequence of path fragments
        :returns: an instance of this class

        If the path is already absolute it will be returned as-is.  A relative
        address is marked by an initial '@', the rest of the address will be
        added to the session path.

        """
        if isinstance(path, Path):
            raise PathError("Cannot be a path")
        path = list(norm_path(path))
        if path[0].startswith('@'):
            assert self.base is not None
            path[0] = path[0][1:]
            if not path[0]:
                path.pop(0)
            path = self.base.path + tuple(path)
        return type(self)(path)

    def __str__(self):
        return PATHSEP.join(self.path)

    def __len__(self):
        return len(self.path)

    def __repr__(self):
        return "<%s.%s for '%s'>" % (
            type(self).__module__,
            type(self).__name__,
            str(self)
        )
