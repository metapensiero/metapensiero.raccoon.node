# -*- coding: utf-8 -*-
# :Project:   metapensiero.raccoon.node -- Invocation
# :Created:   ven 20 ott 2017 16:01:52 CEST
# :Author:    Alberto Berti <alberto@metapensiero.it>
# :License:   GNU General Public License version 3 or later
# :Copyright: Copyright © 2017, 2018 Alberto Berti
#

from collections import namedtuple
import enum

from metapensiero.signal import Executor

from .abc import AbstractDispatcher
from .errors import DispatchError
from .path import Path
from .registry import EndPoint, RPCType


@enum.unique
class DispatchFlags(enum.Enum):
    """Various flags that modify the behavior of the dispatch"""

    LOCAL = 1
    """IF the dispath has to be local only."""


class DispatchDetails(namedtuple(
        'DispatchDetailsNT', ('dispatch_type', 'src_point', 'dst_path',
                              'flags', 'args', 'kwargs'))):
    """Contains the details of a dispatch."""

    def __new__(cls, dispatch_type, src_point, dst_path, *flags, args=None,
                kwargs=None):
        if not isinstance(dispatch_type, RPCType):
            raise ValueError("Invalid dispatch type %r" % dispatch_type)
        if not isinstance(src_point, EndPoint):
            raise ValueError("Invalid source point %r" % src_point)
        if not (len(flags) == 0 or
                all(isinstance(f, DispatchFlags) for f in flags)):
            raise ValueError("Flags can only be values of DispatchFlags")
        if args is None:
            args = ()
        if kwargs is None:
            kwargs = {}
        if not isinstance(dst_path, Path):
            dst_path = Path(dst_path)
        return super().__new__(cls, dispatch_type, src_point, dst_path, flags,
                               args, kwargs)


class Dispatcher(AbstractDispatcher):

    def __init__(self, registry):
        super().__init__()
        self.registry = registry

    def _get_dispatch_method(self, disp_type):
        meth = getattr(self, 'dispatch_{}'.format(disp_type.name.lower()),
                       None)
        return meth

    def dispatch(self, details):
        dispatch_method = self._get_dispatch_method(details.dispatch_type)
        if dispatch_method is None:
            raise DispatchError('Unknown dispatch type %r' %
                                details.dispatch_type)
        try:
            rpc_record = self.registry[details.dst_path]
        except KeyError as e:
            raise DispatchError("Destination path %r not found" %
                                details.dst_path)
        points = rpc_record[details.dispatch_type]
        return dispatch_method(details, points)

    def dispatch_call(self, details, dst_points):
        if len(dst_points) != 1:
            raise DispatchError("Destination point not found for %r" %
                                details.dst_path)
        p, *ignored = dst_points
        assert p is not details.src_point, ("src and dst points cannot be the "
                                            "same")
        return p.call(*details.args, **details.kwargs)

    def dispatch_event(self, details, dst_points):
        # case when the source is the signal/event
        return Executor((p.call for p in dst_points
                         if p is not details.src_point), owner=self,
                        adapt_params=False)(*details.args, **details.kwargs)
