#!/usr/bin/env python3

import argparse
import base64
import datetime
import json
import logging
import multiprocessing as mp
import sys
import time

from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session

from flask import Flask, current_app, request, Response, jsonify
from typing import Dict, Tuple, List, Any

# Constants
VALIDITY = datetime.timedelta(hours=24)

# Logging
logging.basicConfig()
log = logging.getLogger(__name__)
log.setLevel(logging.WARNING)

# Flask app
app = Flask(__name__)


class Base(DeclarativeBase):
    """Base class for the ORM"""

    pass


class AirTag(Base):
    """Representation of an AirTag

    The class is basically just a data wrapper around information related to an
    AirTag. An AirTag is considered unique only based on the advertisement
    received from it, even though more attributes are available (see __eq__ and
    __hash__).

    Attributes:
        data (bytes): the raw bytes representing an AirTag advertisement
        valid_from (datetime.datetime): date and time when the AirTag was seen
        valid_to (datetime.datetime): date and time until which the AirTag is considered valid
        valid_for (datetime.timedelta): time for which the AirTag is still considered valid
        key (bytes): the public key extracted from the BLE advertisement
        addr (bytes): the MAC address of the AirTag extracted from the public key
        body (bytes): the BLE advertisement payload extracted from the public key
    """

    __tablename__ = "airtags"
    id = Column(Integer, primary_key=True)
    _data = Column(String)
    _valid_from = Column(DateTime)
    _valid_to = Column(DateTime)

    def __init__(
        self,
        data: str,
        valid_from: datetime.datetime = None,
        valid_to: datetime.datetime = None,
        *args,
        **kwargs,
    ):
        self.data = data
        self.valid_from = valid_from
        self.valid_to = valid_to

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
    def data(self) -> str:
        return self._data

    @data.setter
    def data(self, value):
        if isinstance(value, bytes):
            # Raw data passed -- encode first
            self._data = base64.b64encode(value).decode()
        elif isinstance(value, str):
            self._data = value
        else:
            raise TypeError()

    @property
    def valid_from(self) -> datetime.datetime:
        return self._valid_from

    @valid_from.setter
    def valid_from(self, value):
        if value is None:
            self._valid_from = datetime.datetime.now()
        elif isinstance(value, str):
            self._valid_from = datetime.datetime.fromisoformat(value)
        elif isinstance(value, datetime.datetime):
            self._valid_from = value
        else:
            raise TypeError("Invalid datetime")

    @property
    def valid_to(self) -> datetime.datetime:
        return self._valid_to

    @valid_to.setter
    def valid_to(self, value):
        if value is None:
            self._valid_to = self._valid_from + VALIDITY
        elif isinstance(value, str):
            self._valid_to = datetime.datetime.fromisoformat(value)
        elif isinstance(value, datetime.datetime):
            self._valid_to = value
        else:
            raise TypeError("Invalid datetime")

    @property
    def valid_for(self) -> datetime.timedelta:
        return self._valid_to - self._valid_from

    @property
    def is_valid(self) -> bool:
        return self._valid_from < datetime.datetime.now() < self._valid_to

    @property
    def key(self) -> bytes:
        return self.extract_key_from_packet(self.data)

    @property
    def body(self) -> bytes:
        adv = self.advertisement_template()
        adv[7:29] = self.key[6:28]
        adv[29] = self.key[0] >> 6
        return adv

    @property
    def addr(self) -> bytes:
        addr = bytearray(self.key[:6])
        addr[0] |= 0b11000000
        return addr[::-1]

    def to_dict(self) -> Dict[str, Any]:
        """Returns a dictionary representation of the object

        Returns:
            Dict[str, Any]: the dictionary representation of the tag
        """
        return {
            "id": self.id,
            "data": self.data,
            "valid_from": self.valid_from.isoformat(),
            "valid_to": self.valid_to.isoformat(),
            "valid_for": str(self.valid_for),
            "valid": self.is_valid,
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


@app.route("/api/v1/airtag", methods=["POST", "PUT"])
def add_tag() -> Tuple[str, int]:
    """REST API function that upserts an AirTag

    API accepts either binary data (only AirTag payload) or a JSON object of
    containing the mandatory field "data" (base64-encoded payload) and optional
    "valid_from" and "valid_to" (ISO date string) fields.

    Returns:
        Tuple[str, int]: HTML error/success message and corresponding status code
    """
    # Dispatch based on payload type
    match request.content_type.split(";")[0]:
        case "application/octet-stream":
            data: bytes = request.get_data()
            valid_from = None
            valid_to = None
        case "application/json":
            data: str = request.json["data"]
            valid_from: str = request.json.get("valid_from", None)
            valid_to: str = request.json.get("valid_to", None)
        case _:
            return "Not supported", 400

    airtag = AirTag(data=data, valid_from=valid_from, valid_to=valid_to)
    with current_app.session() as session, session.begin():
        existing_airtag = session.query(AirTag).filter_by(_data=airtag.data).first()
        if existing_airtag is not None:
            # Update
            existing_airtag.valid_from = valid_from
            existing_airtag.valid_to = valid_to
        else:
            # Insert
            session.add(airtag)

    return "Successfully added AirTag", 200


@app.route("/api/v1/airtag/", methods=["GET"])
def get_tags() -> Response:
    """REST API function that returns a list of tags.
    The function has the following parameters:
    - valid: truthy value on whether to return only currently valid tags (default: False)
    - num: number of tags to return (default: 0 which indicates to return all tags)
    - use_offset: truthy value on whether to round-robin iterate through the tags to return
      (default: False, only effective when valid == True and num > 0)

    Returns:
        Response: Flask Response object with status code 200 and JSON encoded
                  list of tags
    """
    only_valid: bool = request.args.get(
        "valid",
        default=False,
        type=lambda x: x.lower() in ["yes", "y", "true", "t", "1"],
    )
    num_tags: int = request.args.get("num", default=0, type=int)
    offset: bool = request.args.get(
        "offset",
        default=False,
        type=lambda x: x.lower() in ["yes", "y", "true", "t", "1"],
    )
    use_offset: bool = only_valid and num_tags > 0 and offset

    with current_app.session() as session, session.begin():
        query = session.query(AirTag)
        valid_count: int = 0

        if only_valid:
            # Filter AirTags by currently valid AirTags only
            now = datetime.datetime.now()
            query = query.filter(AirTag._valid_from < now, now < AirTag._valid_to)
            valid_count = query.count()
        if use_offset:
            # Offset the query
            # Note: if offset + num_tags > total number of valid tags, only the last total - offset tags are returned
            query = query.offset(current_app.offset)
            # Set new offset or reset if it exceeds the number of available tags
            next_offset: int = current_app.offset + num_tags
            current_app.offset = next_offset if next_offset < valid_count else 0
        if num_tags > 0:
            # Limit query
            query = query.limit(num_tags)

        # Actually execute the query and retrieve the objects
        airtags = query.all()
        airtag_json = jsonify([a.to_dict() for a in airtags])

    return airtag_json


@app.route("/api/v1/airtag/<int:airtag_id>", methods=["GET"])
def get_tag(airtag_id: int) -> Response:
    """REST API function that returns a tag

    Returns:
        Response: Flask Response object with status code 200 and JSON encoded
                  airtag
    """
    with current_app.session() as session, session.begin():
        airtag = session.get(AirTag, airtag_id)
        ret_val = jsonify(airtag.to_dict()) if airtag else ("AirTag not found", 404)
    return ret_val


def api_receiver(interface: str, port: int, session: Session):
    """Starts up a webserver and listens for REST API requests

    Args:
        interface: network interface to listen on (as IP address, e.g., 0.0.0.0)
        port: TCP port to listen on
        session: DB session for persisting data
    """
    app.session = session
    app.offset: int = 0
    app.run(interface, port)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="API server for relaying AirTag advertisements",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "-i",
        "--interface",
        default="0.0.0.0",
        help="Host interface/address to listen on",
    )
    parser.add_argument("-p", "--port", default="8080", help="Port to listen on")
    parser.add_argument(
        "-s",
        "--sqlitedb",
        default="airtags.db",
        help="SQLite database file to persist AirTag information",
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

    # Create database connection
    engine = create_engine("sqlite:///" + args.sqlitedb)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    # Start server
    api_receiver(interface=args.interface, port=args.port, session=Session)
