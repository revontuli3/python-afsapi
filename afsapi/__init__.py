"""
Implements an asynchronous interface for a Frontier Silicon device.

For example internet radios from: Medion, Hama, Auna, Roberts, Revo...

Rewritten to use native coroutines introduced in Python 3.5.
Logic changed to avoid taking an exclusive connection to the device
if not necessary, i.e. when only reading data.




TODO multiroom
TODO presets netRemote.nav.presets
TODO browse tab - netRemote.nav.list
TODO improve error handling with proper exceptions based on status codes and status in return values
TODO set position
TODO netRemote.play.shuffle
TODO netRemote.play.shuffleStatus - not sure where it should work, on our roberts it says 0
TODO alarms
"""


import logging

from lxml import objectify
from enum import Enum


class AFSAPI():

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
