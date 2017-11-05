# -*- coding: utf-8 -*-
# :Project:   raccoon.rocky.node -- registry collection class
# :Created:   gio 26 ott 2017 16:18:28 CEST
# :Author:    Alberto Berti <alberto@metapensiero.it>
# :License:   GNU General Public License version 3 or later
# :Copyright: Copyright © 2017 Arstecnica s.r.l.
#

from collections import defaultdict

from ..path import Path

from .record import RPCRecord
from .errors import RPCError


class Registry:
    """A registry for RPC end points, either *calls* or *subscriptions*.
    """

    def __init__(self):
        self.path_to_record = {}
        self.owner_to_records = defaultdict(set)

    def __contains__(self, item):
        if isinstance(item, Path):
            return item in self.path_to_record
        elif isinstance(item, RPCRecord):
            return item in self.path_to_record.values()
        return False

    def __getitem__(self, path):
        if not isinstance(path, Path):
            path = Path(path)
        return self.path_to_record[path]

    def _index(self, rpc_record, remove=False):
        if remove:
            self._unindex(rpc_record)
        for owner in rpc_record.owners:
            self.owner_to_records[owner].add(rpc_record)

    def _unindex(self, rpc_record):
        for owner in rpc_record.owners:
            self.owner_to_records[owner].remove(rpc_record)
            if len(self.owner_to_records[owner]) == 0:
                del self.owner_to_records[owner]

    def add_point(self, path, point):
        if not isinstance(path, Path):
            path = Path(path)
        record = self.get(path)
        if record is None:
            record = RPCRecord(path)
            self.path_to_record[path] = record
        return point.attach(record)

    def clear(self):
        for rpc_record in self.path_to_record.values():
            self.expunge(rpc_record)

    def expunge(self, rpc_record):
        assert rpc_record.type is not None
        assert rpc_record in self.path_to_record.values()
        self._unindex(rpc_record)
        del rpc_record.registry
        del self.path_to_record[rpc_record.path]
        del rpc_record.path

    def get(self, path, default=None):
        return self.path_to_record.get(path, default)

    def points_for_owner(self, owner):
        return frozenset(p for rec in self.owner_to_records[owner]
                         for p in rec.owned_by(owner))

    def remove_point(self, point):
        if point.rpc_record not in self.path_to_record.values():
            raise RPCError("This point is not registered")
        rec = point.rpc_record
        result = point.detach(point.rpc_record)
        if len(rec) == 0:
            self.expunge(rec)
        return result
