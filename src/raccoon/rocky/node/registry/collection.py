# -*- coding: utf-8 -*-
# :Project:   raccoon.rocky.node -- registry collection class
# :Created:   gio 26 ott 2017 16:18:28 CEST
# :Author:    Alberto Berti <alberto@metapensiero.it>
# :License:   GNU General Public License version 3 or later
# :Copyright: Copyright © 2017 Arstecnica s.r.l.
#

import weakref

from metapensiero.signal import Signal, SignalAndHandlerInitMeta

from ..path import Path

from .record import RPCRecord


class RegistrationSession:

    def __init__(self, context):
        self.context = context
        self.added = []
        self.removed = []

    def add(self, path, rpc_type):
        self.added.append((path, rpc_type))

    def add_point(self, point, path):
        return self.context.registry.add_point(self, point, path)

    def freeze(self):
        self.added = tuple(self.added)
        self.removed = tuple(self.removed)

    def remove(self, path, rpc_type):
        self.removed.append((path, rpc_type))

    def remove_point(self, point, path=None):
        return self.context.registry.remove_point(self, point, path=path)


class OwnerRegistrationContext(set):

    def __init__(self, registry, owner):
        super().__init__()
        self.registry = registry
        self._owner = weakref.ref(owner)
        self.journal = []

    async def __aenter__(self):
        return self._new_session()

    async def __aexit__(self, exc_type, exc_value, traceback):
        sess = self.journal[-1]
        sess.freeze()
        await self.registry.on_session_complete.notify(registry=self.registry,
                                                       session=sess)
        self.registry._gc_context_for(self.owner)

    def _new_session(self):
        sess = RegistrationSession(self)
        self.journal.append(sess)
        return sess

    def clear(self):
        del self.registry
        del self.journal
        super().clear()

    @property
    def owner(self):
        if self._owner is not None:
            return self._owner()


class Registry(metaclass=SignalAndHandlerInitMeta):
    """A registry for RPC end points, either *calls* or *events*.
    """

    on_session_complete = Signal()

    def __init__(self):
        self.path_to_record = {}
        self.owner_to_records = {}

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

    def _gc_context_for(self, owner):
        ctx = self.owner_to_records[owner]
        if len(ctx) == 0:
            ctx.dispose()
            del self.owner_to_records[owner]

    def add_point(self, session, point, path):
        if not isinstance(path, Path):
            path = Path(path)
        record = self.get(path)
        if record is None:
            record = RPCRecord(path)
            record.registry = self
            self.path_to_record[path] = record
            endpoint_is_new = True
        else:
            endpoint_is_new = point.rpc_type not in record
        point.attach(record)
        session.context.add(record)
        if endpoint_is_new:
            session.add(path, point.rpc_type)
        return point

    def clear(self):
        for rpc_record in self.path_to_record.values():
            self.expunge(rpc_record)

    def expunge(self, rpc_record):
        assert rpc_record in self.path_to_record.values()
        if len(rpc_record) > 0:
            for own in rpc_record.owners:
                self.owner_to_records[own].discard(rpc_record)
                self._gc_context_for(own)
        del rpc_record.registry
        del self.path_to_record[rpc_record.path]
        del rpc_record.path

    def get(self, path, default=None):
        return self.path_to_record.get(path, default)

    def new_session_for(self, owner):
        if owner not in self.owner_to_records:
            self.owner_to_records[owner] = ctx = OwnerRegistrationContext(
                self, owner)
        else:
            ctx = self.owner_to_records[owner]
        return ctx

    def points_for_owner(self, owner):
        return frozenset(p for rec in self.owner_to_records[owner]
                         for p in rec.owned_by(owner))

    def remove_point(self, session, point, path=None):
        if path is None:
            records = set(point.rpc_records)
        else:
            if not isinstance(path, Path):
                path = Path(path)
            records = {self[path]}
        for rec in records:
            point.detach(rec)
            if point.rpc_type not in rec:
                session.remove(rec.path, point.rpc_type)
            if len(rec) == 0:
                self.expunge(rec)
            elif point.owner not in rec.owners:
                session.context.discard(rec)
        return point
