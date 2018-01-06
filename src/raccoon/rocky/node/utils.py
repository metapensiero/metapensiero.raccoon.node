# -*- coding: utf-8 -*-
# :Project:   raccoon.rocky.node -- utilities
# :Created:   mar 24 ott 2017 13:47:49 CEST
# :Author:    Alberto Berti <alberto@metapensiero.it>
# :License:   GNU General Public License version 3 or later
# :Copyright: Copyright © 2017, 2018 Alberto Berti
#

import logging
from pprint import pformat
from textwrap import indent


NOISY_ERROR_LOGGER = logging.Logger.error


def log_noisy_error(logger, *args, **kwargs):
    NOISY_ERROR_LOGGER(logger, *args, **kwargs)


def _log(logger, message, *args, **kw):
    if not logger.isEnabledFor(logging.DEBUG):
        return
    if args:
        message = message % args
    for name, value in kw.items():
        if value:
            s = indent(pformat(value, width=160), '    ')
            message += '\n  %s:\n%s' % (name, s)
    logger.debug(message)


class CollectionDescriptor:
    """A simple descriptor to initialize and store a collection per
    instance."""

    name = None
    """The name of the descriptor"""

    def __init__(self, collection_factory):
        self.collection_factory = collection_factory

    def __delete__(self, instance):
        del instance.__dict__[self.name]

    def __get__(self, instance, owner):
        assert instance is not None
        if self.name not in instance.__dict__:
            return instance.__dict__.setdefault(
                self.name, self.collection_factory())
        else:
            return instance.__dict__[self.name]

    def __set_name__(self, owner, name):
        self.name = name


def build_instance_mapping(instance, member_names):
    """From a list of class member names, get their bound version."""
    return {name: getattr(instance, mname) for mname,
            name in member_names.items()}


def calc_signal_path(node_path, node_context, signal_name):
    """Calculate the path of a signal."""
    assert isinstance(signal_name, str)
    if signal_name == '.':
        p = node_path
    else:
        p = node_path + signal_name
    return p


def calc_call_path(node_path, node_context, call_name):
    """Calculate the path of a call endpoint."""
    return calc_signal_path(node_path, node_context, call_name)


def calc_handler_target_path(node_path, node_context, handler_path):
    """Calculate the target path of an handler."""
    assert isinstance(handler_path, str)
    if handler_path == '.':
        p = node_path
    else:
        p = node_path.resolve(handler_path, node_context)
    return p


def filter_signals(signals, exclude_names):
    """Filter the signals by name.

    :param sigals: signals to filter
    :type signals: a mapping composed of (signal_name, signal) tuples
    :param exclude_names: names to exclude
    :returns: a mapping containing the filtered names
    """
    return {n: sig for n, sig in signals.items() if
            (n not in exclude_names) and sig is not None}
