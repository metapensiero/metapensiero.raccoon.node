# -*- coding: utf-8 -*-
# :Progetto:  raccoon.rocky.node -- proxy object
# :Creato:    ven 25 nov 2016 14:05:52 CET
# :Autore:    Alberto Berti <alberto@metapensiero.it>
# :Licenza:   GNU General Public License version 3 or later
#

from .path import Path

class ProxyError(Exception):
    pass


class Proxy:
    """This is a glimpse into the 'other side', a medium towards
    addressability of a possibly remote tree of objects.
    """

    def __init__(self, node, path):
        self.__node = node
        if isinstance(path, Path):
            self.__path = path
        else:
            self.__path = node.node_path.resolve(path, node.node_context)
        self.__name = self.__path[-1]

    def __str__(self):
        return str(self.__path)

    def __getattr__(self, name):
        if name.startswith('_'):
            raise AttributeError('No private members')
        return self.__class__(self.__node, str(self.__path + name))

    def __call__(self, *args, **kwargs):
        if not self.__name:
            raise ProxyError("No call function or no path")
        return self.__node.__class__.manager.call(self.__node, self.__path,
                                                  *args, **kwargs)

    def connect(self, handler):
        return self.__node.__class__.manager.connect(self.__node, self.__path,
                                                     handler)

    def disconnect(self, handler):
        return self.__node.__class__.manager.disconnect(self.__node, self.__path,
                                                        handler)

    def notify(self, *args, **kwargs):
        manager = self.__node.__class__.manager
        return self.__node.__class__.manager.notify(manager.get_point(self.__node),
                                                    self.__path, *args, **kwargs)
