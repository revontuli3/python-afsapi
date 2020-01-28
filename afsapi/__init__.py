"""
Implements an asynchronous interface for a Frontier Silicon device.

For example internet radios from: Medion, Hama, Auna, Roberts, Revo...

Rewritten to use native coroutines introduced in Python 3.5.
Logic changed to avoid taking an exclusive connection to the device
if not necessary, i.e. when only reading data.

API methods:
    'GET',
    'SET',
    'LIST_GET_NEXT',
    'CREATE_SESSION',
    'DELETE_SESSION',
    'GET_NOTIFIES' # requires a session, not used here


flammy's documentation was used to develop this:
https://github.com/flammy/fsapi/blob/master/FSAPI.md

TODO multiroom
TODO presets netRemote.nav.presets
TODO browse tab - netRemote.nav.list
TODO improve error handling with proper exceptions based on status codes and status in return values
TODO maybe use properties with setters and getters?
TODO set position
TODO netRemote.play.shuffle
TODO netRemote.play.shuffleStatus - not sure where it should work, on our roberts it says 0
netRemote.spotify.status - 2 playing, 3 paused, 0 not running
TODO alarms
"""


import asyncio
import aiohttp
import logging
#import traceback

from lxml import objectify
from enum import Enum


class AFSAPI():
    """Builds the interface to a Frontier Silicon device."""

    DEFAULT_TIMEOUT_IN_SECONDS = 1

    # states TODO change to enum
    PLAY_STATES = {
        0: 'stopped',
        1: 'unknown',
        2: 'playing',
        3: 'paused',
    }

    class Controls(Enum):
        PLAY = 1
        PAUSE = 2
        NEXT = 3
        PREVIOUS = 4

    # implemented API calls
    API_CALLS = {
        # sys
        'friendly_name': 'netRemote.sys.info.friendlyName',
        'power': 'netRemote.sys.power',
        'mode': 'netRemote.sys.mode',
        'valid_modes': 'netRemote.sys.caps.validModes',
        'equalisers': 'netRemote.sys.caps.eqPresets',
        'sleep': 'netRemote.sys.sleep',
        # volume
        'volume_steps': 'netRemote.sys.caps.volumeSteps',
        'volume': 'netRemote.sys.audio.volume',
        'mute': 'netRemote.sys.audio.mute',
        # play
        'status': 'netRemote.play.status',
        'name': 'netRemote.play.info.name',
        'control': 'netRemote.play.control',
        'position': 'netRemote.play.position',
        # info
        'text': 'netRemote.play.info.text',
        'artist': 'netRemote.play.info.artist',
        'album': 'netRemote.play.info.album',
        'graphic_uri': 'netRemote.play.info.graphicUri',
        'duration': 'netRemote.play.info.duration'
    }

    def __init__(self, fsapi_device_url, pin, timeout=DEFAULT_TIMEOUT_IN_SECONDS, intrusive=False):
        """
        Initialize the connection to a Frontier Silicon device.
        
        :param str fsapi_device_url
        :param str pin
        :param str timeout
        :param bool intrusive: Whether a new session should be created for read calls
        """

        self.fsapi_device_url = fsapi_device_url
        self.pin = pin
        self.timeout = timeout
        self.intrusive = intrusive

        self.sid = None
        self.__webfsapi = None
        self.__modes = None
        self.__volume_steps = None
        self.__equalisers = None
        self.__session = aiohttp.ClientSession()

    async def close(self):
        """Close connection to the device and http sessions."""

        if self.sid is not None:
            await self.call('DELETE_SESSION', None, False)
        await self.__session.close()

    # async context manager

    async def __aenter__(self):
        return self

    async def __aexit__(self, *excinfo):
        await self.close()


    # http request helpers

    async def get_fsapi_endpoint(self):
        """Parse the fsapi endpoint from the device url."""
        
        endpoint = await self.__session.get(self.fsapi_device_url, timeout = self.timeout)
        text = await endpoint.text(encoding='utf-8')
        doc = objectify.fromstring(text)
        return doc.webfsapi.text

    async def create_session(self):
        """Create a session on the frontier silicon device."""
        
        req_url = '%s/%s' % (self.__webfsapi, 'CREATE_SESSION')
        sid = await self.__session.get(req_url, params={'pin': self.pin},
                                            timeout = self.timeout)
        text = await sid.text(encoding='utf-8')
        doc = objectify.fromstring(text)
        return doc.sessionId.text

    async def call(self, path, extra=None, create_session=True):
        """Execute a frontier silicon API call."""
        
        try:
            if not self.__webfsapi:
                self.__webfsapi = await self.get_fsapi_endpoint()

            if create_session and not self.sid:
                self.sid = await self.create_session()

            if not isinstance(extra, dict):
                extra = {}

            params = {}
            params['pin'] = self.pin
            
            if self.sid is not None:
                params['sid'] = self.sid
            
            params.update(**extra)

            req_url = ('%s/%s' % (self.__webfsapi, path))
            result = await self.__session.get(req_url, params=params,
                                                   timeout = self.timeout)

            if result.status == 200:
                text = await result.text(encoding='utf-8')
            else: # TODO should happen only when the session is invalid, not for else
                #TODO what does this actually do?
                self.sid = await self.create_session()
                params = {'pin': self.pin, 'sid': self.sid}
                params.update(**extra)
                result = await self.__session.get(req_url, params=params,
                                                    timeout = self.timeout)
                text = await result.text(encoding='utf-8')

            return objectify.fromstring(text)
        except Exception as e: #TODO improve error handling
            logging.info('AFSAPI Exception: ' +str(e))

        return None

    # Helper methods

    # Handlers
    async def handle_get(self, item):
        """Helper method for reading a value by using the fsapi API."""
        res = await self.call(f'GET/{item}', None, False)
        return res

    async def handle_set(self, item, value):
        """Helper method for setting a value by using the fsapi API."""
        doc = await self.call('SET/{}'.format(item), dict(value=value))
        if doc is None:
            return None

        return doc.status == 'FS_OK'

    async def handle_text(self, item):
        """Helper method for fetching a text value."""
        doc = await self.handle_get(item)
        if doc is None:
            return None

        return doc.value.c8_array.text or None

    async def handle_int(self, item):
        """Helper method for fetching a integer value."""
        doc = await self.handle_get(item)
        if doc is None:
            return None

        return int(doc.value.u8.text) or None

    # returns an int, assuming the value does not exceed 8 bits
    async def handle_long(self, item):
        """Helper method for fetching a long value. Result is integer."""
        doc = await self.handle_get(item)
        if doc is None:
            return None

        return int(doc.value.u32.text) or None

    async def handle_list(self, item):
        """Helper method for fetching a list(map) value."""
        # TODO more than 100 items
        doc = await self.call('LIST_GET_NEXT/'+item+'/-1', dict(
            maxItems=100,
        ), False)

        if doc is None:
            return []

        if not doc.status == 'FS_OK':
            return []

        ret = []
        for index, item in enumerate(list(doc.iterchildren('item'))):
            temp = {'band': index}
            for field in list(item.iterchildren()):
                temp[field.get('name')] = list(field.iterchildren()).pop()
            ret.append(temp)

        return ret

    async def collect_labels(self, items):
        """Helper methods for extracting the labels from a list with maps."""
        if items is None:
            return []

        return [str(item['label']) for item in items if item['label']]

    # API implementation starts here

    # sys
    async def get_friendly_name(self):
        """Get the friendly name of the device."""
        return (await self.handle_text(self.API_CALLS.get('friendly_name')))

    async def set_friendly_name(self, value):
        """Set the friendly name of the device."""
        return (await self.handle_set(
            self.API_CALLS.get('friendly_name'), value))

    async def get_power(self):
        """Check if the device is on."""
        power = (await self.handle_int(self.API_CALLS.get('power')))
        return bool(power)

    async def set_power(self, value=False):
        """Power on or off the device."""
        power = (await self.handle_set(
            self.API_CALLS.get('power'), int(value)))
        return bool(power)

    async def get_modes(self):
        """Get the modes supported by this device."""
        if not self.__modes:
            self.__modes = await self.handle_list(
                self.API_CALLS.get('valid_modes'))

        return self.__modes

    async def get_mode_list(self):
        """Get the label list of the supported modes."""
        self.__modes = await self.get_modes()
        return (await self.collect_labels(self.__modes))

    async def get_mode(self):
        """Get the currently active mode on the device (DAB, FM, Spotify)."""
        mode = None
        int_mode = (await self.handle_long(self.API_CALLS.get('mode')))
        modes = await self.get_modes()
        for temp_mode in modes:
            if temp_mode['band'] == int_mode:
                mode = temp_mode['label']

        return str(mode)

    async def set_mode(self, value):
        """Set the currently active mode on the device (DAB, FM, Spotify)."""
        mode = -1
        modes = await self.get_modes()
        for temp_mode in modes:
            if temp_mode['label'] == value:
                mode = temp_mode['band']

        return (await self.handle_set(self.API_CALLS.get('mode'), mode))

    async def get_volume_steps(self):
        """Read the maximum volume level of the device."""
        if not self.__volume_steps:
            self.__volume_steps = await self.handle_int(
                self.API_CALLS.get('volume_steps'))

        return self.__volume_steps

    # Volume
    async def get_volume(self):
        """Read the volume level of the device."""
        vol = (await self.handle_int(self.API_CALLS.get('volume')))
        return 0 if vol is None else vol

    async def set_volume(self, value):
        """Set the volume level of the device."""
        return (await self.handle_set(self.API_CALLS.get('volume'), value))
        #TODO maybe do the same hack with 0

    # Mute
    async def get_mute(self):
        """Check if the device is muted."""
        mute = (await self.handle_int(self.API_CALLS.get('mute')))
        return bool(mute)

    async def set_mute(self, value=False):
        """Mute or unmute the device."""
        mute = (await self.handle_set(self.API_CALLS.get('mute'), int(value)))
        return bool(mute)

    async def get_play_status(self):
        """Get the play status of the device."""
        status = await self.handle_int(self.API_CALLS.get('status'))
        return self.PLAY_STATES.get(status)

    async def get_play_name(self):
        """Get the name of the played item."""
        return (await self.handle_text(self.API_CALLS.get('name')))

    async def get_play_text(self):
        """Get the text associated with the played media."""
        return (await self.handle_text(self.API_CALLS.get('text')))

    async def get_play_artist(self):
        """Get the artists of the current media(song)."""
        return (await self.handle_text(self.API_CALLS.get('artist')))

    async def get_play_album(self):
        """Get the songs's album."""
        return (await self.handle_text(self.API_CALLS.get('album')))

    async def get_play_graphic(self):
        """Get the album art associated with the song/album/artist."""
        return (await self.handle_text(self.API_CALLS.get('graphic_uri')))

    async def get_play_duration(self):
        """Get the duration of the played media."""
        return (await self.handle_long(self.API_CALLS.get('duration')))

    async def get_play_position(self):
        """Get the position of the played media."""
        return (await self.handle_long(self.API_CALLS.get('position')))


    # play controls

    async def play_control(self, value):
        """Control the player of the device."""
        return (await self.handle_set(self.API_CALLS.get('control'), value))

    async def play(self):
        """Play media."""
        return (await self.play_control(1))

    async def pause(self):
        """Pause playing."""
        return (await self.play_control(2))

    async def forward(self):
        """Next media."""
        return (await self.play_control(3))

    async def rewind(self):
        """Previous media."""
        return (await self.play_control(4))

    async def get_equalisers(self):
        """Get the equaliser modes supported by this device."""
        if not self.__equalisers:
            self.__equalisers = await self.handle_list(
                self.API_CALLS.get('equalisers'))

        return self.__equalisers

    async def get_equaliser_list(self):
        """Get the label list of the supported modes."""
        self.__equalisers = await self.get_equalisers()
        return (await self.collect_labels(self.__equalisers))

    # Sleep
    async def get_sleep(self):
        """Check when and if the device is going to sleep."""
        return (await self.handle_long(self.API_CALLS.get('sleep')))

    async def set_sleep(self, value=False):
        """Set device sleep timer."""
        return (await self.handle_set(self.API_CALLS.get('sleep'), int(value)))
