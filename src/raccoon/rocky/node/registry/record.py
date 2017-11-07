from raccoon.rocky.node.path import Path

from .point import EndPoint, TypedKey
from .utils import RPCType


class RPCRecord:
    """Stores resources connected to a path.

    :type registry: :class:`Registry` instance
    :param registry: the related registry
    :type path: str
    :param path: the name of the RPC
    :type rpc_type: str
    :param rpc_type: the kind of RPC, see `RPCType`
    """

    registry = None

    def __init__(self, path):
        if not isinstance(path, Path):
            path = Path(path)
        self.path = path
        self.points = {}

    def __contains__(self, point_or_key):
        if isinstance(point_or_key, TypedKey):
            return point_or_key in self.points
        elif isinstance(point_or_key, EndPoint):
            return point_or_key in self.points.values()
        return False

    def __getitem__(self, key_or_type_or_owner):
        if isinstance(key_or_type_or_owner, TypedKey):
            return self.points[key_or_type_or_owner]
        elif isinstance(key_or_type_or_owner, RPCType):
            return frozenset(self.points[k] for k in self.points
                             if k.rpc_type is key_or_type_or_owner)
        elif key_or_type_or_owner in self.owners:
            return self.owned_by(key_or_type_or_owner)
        raise ValueError("The key is of the wrong type")

    def __len__(self):
        return len(self.points)

    def __repr__(self):
        return ("<{name} for '{path}'> "
                "points: {points}".format(
                    name=self.__class__.__name__,
                    path=self.path,
                    points=len(self)
                ))

    def _reindex(self):
        if self.registry is not None:
            self.registry._index(self, remove=True)

    def add(self, point):
        assert type(point) is not EndPoint and isinstance(point, EndPoint)
        self.points[point.key] = point
        point.rpc_records.add(self)
        self._reindex()

    def is_empty(self, context=None):
        return len(self.points) == 0

    def is_local(self):
        """Does this rpc_record represents some local resource?"""
        return (len(self) > 0 and any(map(lambda p: not p.remote,
                                          self.points.values())))

    @property
    def owners(self):
        return frozenset(key.owner for key in self.points)

    def owned_by(self, owner):
        return frozenset(filter(lambda p: p.key.owner is owner,
                                self.points.values()))

    def remove(self, point):
        assert type(point) is not EndPoint and isinstance(point, EndPoint)
        del self.points[point.key]
        point.rpc_records.discard(self)
        self._reindex()
