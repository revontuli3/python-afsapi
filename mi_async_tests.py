"""Test of the asynchronous Frontier Silicon interface."""
import asyncio
import traceback
import logging

from afsapi import AFSAPI

URL = 'http://192.168.1.3:80/device'
PIN = 1234
TIMEOUT = 2 # in seconds


async def test_reads(api):
    power = await api.get_power()
    print('Power on: %s' % power)

    end_point = await api.get_fsapi_endpoint()
    print('Endpoint: %s' % end_point)

    friendly_name = await api.get_friendly_name()
    print('Friendly name: %s' % friendly_name)

    modes = await api.get_modes()
    print('Modes: %s' % modes)

    mode_list = await api.get_mode_list()
    print('Mode List: %s' % mode_list)

    equalisers = await api.get_equalisers()
    print('Equaliser: %s' % equalisers)

    equaliser_list = await api.get_equaliser_list()
    print('Equaliser List: %s' % equaliser_list)

    mode = await api.get_mode()
    print('Mode: %s' % mode)

    sleep = await api.get_sleep()
    print('Sleep: %s' % sleep)

    volume = await api.get_volume()
    print('Volume: %s' % volume)

    volume_steps = await api.get_volume_steps()
    print('Volume steps: % s' % volume_steps)

    mute = await api.get_mute()
    print('Is muted: %s' % mute)

    name = await api.get_play_name()
    print('Name: %s' % name)

    text = await api.get_play_text()
    print('Text: %s' % text)

    artist = await api.get_play_artist()
    print('Artist: %s' % artist)

    album = await api.get_play_album()
    print('Album: %s' % album)

    graphic = await api.get_play_graphic()
    print('Graphic: %s' % graphic)

    position = await api.get_play_position()
    print('Position: %s' % position)

    duration = await api.get_play_duration()
    print('Duration: %s' % duration)

    status = await api.get_play_status()
    print('Status: %s' % status)


async def test_with_read():
    async with AFSAPI(URL, PIN, TIMEOUT) as api:
        try:
            await test_reads(api)
        except Exception:
            logging.error(traceback.format_exc())


async def test_finally_read():
    try:
        api = AFSAPI(URL, PIN, TIMEOUT)
        await test_reads(api)
    except Exception:
        logging.error(traceback.format_exc())
    finally:
        await api.close()


async def test_set_play():
    async with AFSAPI(URL, PIN, TIMEOUT) as api:
        try:
            status = await api.get_play_status()
            print(f'Status: {status}')

            forward = await api.forward()
            print(f'Next succeeded? - {forward}')

            await asyncio.sleep(5)

            rewind = await api.rewind()
            print(f'Prev succeeded? - {rewind}')
        except Exception:
            logging.error(traceback.format_exc())



asyncio.run(test_with_read())
#asyncio.run(test_finally_read())

#asyncio.run(test_set_play())
