# -*- coding: utf-8 -*-
# :Project:   raccoon.rocky.node -- WAMP Node abc
# :Created:   mer 18 ott 2017 19:51:50 CEST
# :Author:    Alberto Berti <alberto@metapensiero.it>
# :License:   GNU General Public License version 3 or later
# :Copyright: Copyright © 2016, 2017 Arstecnica s.r.l.
#

from abc import ABCMeta, abstractmethod


class AbstractWAMPNode(metaclass=ABCMeta):

    @abstractmethod
    def node_register(self):
        pass

    @abstractmethod
    def node_unregister(self):
        pass

    @classmethod
    def __subclasshook__(cls, subcls):
        from .signal import WAMPInitMeta
        result = False
        if issubclass(type(subcls), WAMPInitMeta):
            for name in ('on_node_register',  'on_node_registration_success',
                         'on_node_registration_failure', 'on_node_unregister',
                         'node_registered'):
                if not any(name in b.__dict__ for b in subcls.__mro__):
                    break
            else:
                result = True
        return result
