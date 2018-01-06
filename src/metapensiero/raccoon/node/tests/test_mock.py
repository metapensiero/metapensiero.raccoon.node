# -*- coding: utf-8 -*-
# :Project:   metapensiero.raccoon.node -- test mock objects
# :Created:   lun 19 ott 2015 19:35:42 CEST
# :Author:    Alberto Berti <alberto@metapensiero.it>
# :License:   GNU General Public License version 3 or later
# :Copyright: © 2016, 2017, 2018 Alberto Berti
#

import pytest


@pytest.mark.asyncio
async def test_call_not_registered_fails(wamp_session):
    with pytest.raises(ValueError):
        await wamp_session.call('pippo.pluto')


@pytest.mark.asyncio
async def test_call_registered_succeeds(wamp_session):
    async def pluto(**kwargs):
        assert 'details' in kwargs
        return 'called'
    await wamp_session.register(pluto, 'pippo.pluto')
    result = await wamp_session.call('pippo.pluto')
    assert result == 'called'


@pytest.mark.asyncio
async def test_wildcard_registration(wamp_session):

    async def exact(**kwargs):
        assert 'details' in kwargs
        return 'called exact'
    await wamp_session.register(exact, 'pippo.pluto.pollo')
    async def wildcard(**kwargs):
        assert 'details' in kwargs
        assert kwargs['details'].procedure == 'pippo.pluto.pollo.palombo'
        return 'called wildcard'
    await wamp_session.register(wildcard, 'pippo.pluto.pollo.')
    result = await wamp_session.call('pippo.pluto.pollo')
    assert result == 'called exact'
    result = await wamp_session.call('pippo.pluto.pollo.palombo')
    assert result == 'called wildcard'
    with pytest.raises(ValueError):
        await wamp_session.call('pippo.pluto.pollo.polletto.micio')


@pytest.mark.asyncio
async def test_subscriber_and_publisher(wamp_session, wamp_session2, events):
    sub1_called = False
    sub2_called = False
    events.define('w', 'w2')

    async def sub1(**kwargs):
        nonlocal sub1_called
        assert 'details' in kwargs
        sub1_called = True
        events.w.set()

    async def sub2(**kwargs):
        nonlocal sub2_called
        assert 'details' in kwargs
        sub2_called = True
        events.w2.set()

    await wamp_session.subscribe(sub1, 'pippo.pluto.event1')
    await wamp_session.subscribe(sub2, 'pippo.pluto.event2')

    wamp_session2.publish('pippo.pluto.event1')
    await events.w.wait()
    with pytest.raises(events.TimeoutError):
        await events.wait_for(events.w2, 2)
    assert sub1_called == True
    assert sub2_called == False
