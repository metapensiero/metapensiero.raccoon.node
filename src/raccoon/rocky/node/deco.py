# -*- coding: utf-8 -*-
# :Project:   raccoon.rocky.node -- @call decorator
# :Created:   mer 18 ott 2017 19:51:50 CEST
# :Author:    Alberto Berti <alberto@metapensiero.it>
# :License:   GNU General Public License version 3 or later
# :Copyright: Copyright © 2016, 2017, 2018 Alberto Berti
#

from .errors import RPCError
from . import SPEC_CONTAINER_MEMBER_NAME


class CallDecoMeta(type):
    """A metaclass to deal with the double protocol of decorators about
    their definition.
    """

    def __call__(cls, method_or_name=None):
        if method_or_name is None or isinstance(method_or_name, str):
            res = super().__call__(method_or_name)
        else:
            res = super().__call__()(method_or_name)
        return res


class CallNameDecorator(metaclass=CallDecoMeta):
    "A decorator used to mark a method as a call."

    def __init__(self, call_name=None):
        self.call_name = call_name
        if call_name and '.' in call_name and len(call_name) > 1:
            raise RPCError('Call names cannot contain dots')

    def __call__(self, method):
        setattr(method, SPEC_CONTAINER_MEMBER_NAME,
                {'kind': 'call', 'name': self.call_name})
        return method

    @classmethod
    def is_call(cls, name, value):
        """Detect an a call and return its wanted name."""
        call_name = False
        if callable(value) and hasattr(value, SPEC_CONTAINER_MEMBER_NAME):
                spec = getattr(value, SPEC_CONTAINER_MEMBER_NAME)
                if spec['kind'] == 'call':
                    call_name = spec['name']
        return call_name


call = CallNameDecorator
