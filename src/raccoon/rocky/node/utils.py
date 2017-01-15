# -*- coding: utf-8 -*-
# :Project:   raccoon.rocky.node -- utilities
# :Created:   mer 28 dic 2016 11:59:15 CET
# :Author:    Alberto Berti <alberto@metapensiero.it>
# :License:   GNU General Public License version 3 or later
# :Copyright: Copyright (C) 2016, 2017 Arstecnica s.r.l.
#

import asyncio
import contextlib

from metapensiero.asyncio import transaction


def gather(*coros, loop=None, task=None):
    """A version of ``asyncio.gather()`` that automatically takes transaction into
    account."""
    trans = transaction.get(None, loop=loop, task=task)
    if trans:
        res = trans.gather(*coros)
    else:
        res = asyncio.gather(*coros, loop=loop)
    return res


def add_to_transaction(*coros, loop=None, task=None):
    """Optionally add coros if a transaction is in place."""
    trans = transaction.get(None, loop=loop, task=task)
    if trans:
        res = trans.add(*coros)
    else:
        res = [asyncio.ensure_future(c, loop=loop) for c in coros]
    if len(coros) == 1:
        return res[0]
    else:
        return res


@contextlib.contextmanager
def in_transaction(*, loop=None, task=None):
    trans = transaction.get(None, loop=loop, task=task)
    if trans:
        trans.__enter__()
    yield trans
    if trans:
        trans.__exit__(None, None, None)
