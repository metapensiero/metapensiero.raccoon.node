# -*- coding: utf-8 -*-
# :Project:   metapensiero.raccoon.node -- proxy object
# :Created:   ven 25 nov 2016 14:05:52 CET
# :Author:    Alberto Berti <alberto@metapensiero.it>
# :License:   GNU General Public License version 3 or later
# :Copyright: © 2016, 2017, 2018 Alberto Berti
#

from .path import Path
from . import serialize


class ProxyError(Exception):
    pass


class Proxy:
    """This is a glimpse into the *other side*, a medium towards
    addressability of a possibly remote tree of objects.
    """

    node_path = None
    """The path of the node this object is proxing."""

    def __init__(self, node, path):
        self.__node = node
        if isinstance(path, Path):
            self.node_path = path
        else:
            self.node_path = node.node_path.resolve(path, node.node_context)
        self.__name = self.node_path[-1]

    def __str__(self):
        return str(self.node_path)

    def __getattr__(self, name):
        if name.startswith('_'):
            raise AttributeError('No private members')
        return type(self)(self.__node, self.node_path + name)

    def __call__(self, *args, **kwargs):
        if not self.__name:
            raise ProxyError("No call function or no path")
        manager = self.__node.__class__.manager
        return manager.call(self.__node, self.node_path, *args, **kwargs)

    def connect(self, handler):
        manager = self.__node.__class__.manager
        return manager.connect(self.__node, self.node_path, handler)

    def disconnect(self, handler):
        manager = self.__node.__class__.manager
        return manager.disconnect(self.__node, self.node_path, handler)

    def notify(self, *args, **kwargs):
        manager = self.__node.__class__.manager
        return manager.notify(manager.get_point(self.__node), self.node_path,
                              *args, **kwargs)


class ProxySerializer(serialize.Serializable):

    def node_deserialize(self, value, end_node=None):
        raise serialize.SerializationError(
                "It's an error to deserialize a NodeProxy"
            )

    def node_serialize(self, instance, src_node=None):
        if instance.node_path is None:
            raise serialize.SerializationError(
                "This instance cannot be serialized"
            )
        # this uses the same serialization key of the Node class, there's no
        # point in having a proper serialization form for NodeProxy, it's a
        # stub
        return serialize.Serialized(
            str(instance.node_path), 'raccoon.node.WAMPNode')


serialize.define('raccoon.node.NodeProxy', serializer=ProxySerializer(),
                 cls=Proxy)
