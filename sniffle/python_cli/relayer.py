#!/usr/bin/env python3

import argparse
import base64
import datetime
import json
import logging
import sys
import time
import requests

from sniffle_hw import BLE_ADV_AA, SniffleHW
from typing import Dict, Tuple, List

# Constants
VALIDITY = datetime.timedelta(hours=24)

# Logging
logging.basicConfig()
log = logging.getLogger(__name__)
log.setLevel(logging.WARNING)


class AirTag(object):
    """Representation of an AirTag

    The class is basically just a data wrapper around information related to an
    AirTag. An AirTag is considered unique only based on the advertisement
    received from it, even though more attributes are available (see __eq__ and
    __hash__).

    Attributes:
        data (bytes): the raw bytes representing an AirTag advertisement
        recorded (datetime.datetime): date and time when the AirTag was seen
        valid_for (datetime.timedelta): time for which the AirTag is considered valid
        key (bytes): the public key extracted from the BLE advertisement
        advaddr (bytes): the MAC address of the AirTag extracted from the public key
        advbody (bytes): the BLE advertisement payload extracted from the public key
    """

    def __init__(
        self,
        data: bytes,
        recorded: datetime.datetime = None,
        valid_for: datetime.timedelta = VALIDITY,
        *args,
        **kwargs,
    ):
        self._data: bytes = data
        self._recorded: datetime.datetime = recorded or datetime.datetime.now()
        self._valid_for: datetime.timedelta = valid_for

    def __eq__(self, other):
        # Only the actual tag data is used for determining equality
        return self.data == other.data

    def __ne__(self, other):
        return not self == other

    def __gt__(self, other):
        return NotImplemented

    def __ge__(self, other):
        return NotImplemented

    def __hash__(self):
        # Similar to __eq__, only want to use the tag data for checking equality
        return hash(self.data)

    @property
    def data(self) -> bytes:
        return self._data

    @data.setter
    def data(self, value):
        self._data = value

    @property
    def recorded(self) -> datetime.datetime:
        return self._recorded

    @recorded.setter
    def recorded(self, value):
        if isinstance(value, str):
            self._recorded = datetime.fromisoformat(str)
        elif isinstance(value, datetime.datetime):
            self._recorded = value
        else:
            raise TypeError("Invalid datetime")

    @property
    def valid_for(self) -> datetime.timedelta:
        return self._valid_for

    @valid_for.setter
    def valid_for(self, value):
        self._valid_for = value

    @property
    def key(self) -> bytes:
        return self.extract_key_from_packet(self.data)

    @property
    def advbody(self) -> bytes:
        adv = self.advertisement_template()
        adv[7:29] = self.key[6:28]
        adv[29] = self.key[0] >> 6
        return adv

    @property
    def advaddr(self) -> bytes:
        addr = bytearray(self.key[:6])
        addr[0] |= 0b11000000
        return addr[::-1]

    def to_dict(self) -> Dict[str, str]:
        """Returns a dictionary representation of the object

        Returns:
            Dict[str, str]: the dictionary representation of the tag
        """
        return {
            "data": base64.b64encode(self.data).decode(),
            "recorded": self.recorded.isoformat(),
            "valid_for": str(self.valid_for),
        }

    def to_json(self) -> str:
        """Returns a JSON representation of the object

        Returns:
            str: the JSON representation of the tag
        """
        return json.dumps(self.to_dict())

    @classmethod
    def advertisement_template(cls) -> bytes:
        """Creates a template for the advertisement, pre-filled with the fixed data

        Returns:
            bytes: the template pre-filled with the fixed bytes
        """
        adv = ""
        adv += "1e"  # length (30)
        adv += "ff"  # manufacturer specific data
        adv += "4c00"  # company ID (Apple)
        adv += "1219"  # offline finding type and length
        adv += "00"  # state
        for _ in range(22):  # key[6:28]
            adv += "00"
        adv += "00"  # first two bits of key[0]
        adv += "00"  # hint
        return bytearray.fromhex(adv)

    @classmethod
    def extract_key_from_packet(cls, adv: bytes) -> bytes:
        """Extracts the public key used by the AirTag from a raw packet

        Args:
            adv (bytes): bytes-like object containing the raw packet data

        Returns:
            bytes: the extracted public key
        """
        if len(adv) == 39:
            adv = adv[2:]
        addr = adv[5::-1]
        key = bytearray(28)
        key[0] = ((adv[35] << 6) & 0b11000000) | (addr[0] & 0b00111111)
        key[1:6] = addr[1:6]
        key[6:28] = adv[13:35]
        return key


def ble_sender(args) -> None:
    """Sends advertisements for tags

    Args:
        args: list of program arguments with configuration options
    """
    # Basic hardware setup
    hw = SniffleHW(args.serport)
    # Channel setup
    hw.cmd_chan_aa_phy(37, BLE_ADV_AA, 0)
    hw.cmd_pause_done(True)
    # Do not follow connections
    hw.cmd_follow(False)
    # Do not actually sniff data (unreasonable RSSI filter)
    hw.cmd_rssi(-1)
    hw.cmd_mac()
    hw.cmd_auxadv(False)
    # Advertise roughly every <frequency> ms
    hw.cmd_adv_interval(args.frequency)
    # Reset preloaded encrypted connection interval changes
    hw.cmd_interval_preload()

    # Scan response data
    devname = b"RelayTag"
    scanrsp = bytes([len(devname) + 1, 0x09]) + devname

    while True:
        response = requests.get(
            "http://playground.fhofhammer.de/api/v1/airtag/",
            params={
                "valid": "true",
                "num": "5",
                "offset": "true",
            },
        )

        try:
            json_tags = response.json()
        except json.decoder.JSONDecodeError:
            continue

        for json_tag in json_tags:
            tag = AirTag(data=base64.b64decode(json_tag["data"]))
            log.debug(
                f"Advertising tag {':'.join(map(lambda x: format(x, 'x'), tag.advaddr))} with body {tag.advbody.hex(' ', 1)}"
            )
            # Set advertisement MAC address
            hw.cmd_setaddr(tag.advaddr, is_random=True)
            # Start advertising
            hw.cmd_advertise(tag.advbody, scanrsp)
            # Briefly advertise, then switch over to the next tag
            time.sleep(
                (args.frequency / 1000) * 5
            )  # Advertise ~4-5 times before switching


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="AirTag advertisement relayer via Sniffle",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "-s", "--serport", default=None, help="Sniffle serial port name"
    )
    parser.add_argument(
        "-f",
        "--frequency",
        default=500,
        type=int,
        help="Frequency (in ms) in which to send out advertisements",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        dest="verbosity",
        action="count",
        default=0,
        help="print verbose output. Specify multiple times for increasing verbosity",
    )

    args = parser.parse_args()

    # Set log level based on given verbosity
    verb_levels = [logging.WARNING, logging.INFO, logging.DEBUG]
    log.setLevel(verb_levels[min(len(verb_levels) - 1, args.verbosity)])

    ble_sender(args)
