#!/usr/bin/env python3

import argparse
import logging
import multiprocessing as mp
import queue

import requests as rq
from packet_decoder import (
    AdvDirectIndMessage,
    AdvIndMessage,
    AdvNonconnIndMessage,
    AdvScanIndMessage,
    DPacketMessage,
)
from sniffle_hw import (
    DebugMessage,
    MeasurementMessage,
    PacketMessage,
    SniffleHW,
    StateMessage,
)

# Logging
logging.basicConfig()
log = logging.getLogger(__name__)
log.setLevel(logging.INFO)


def ble_receiver(args, tags, lock):
    """Communicates with the Sniffle firmware to record AirTag advertisements

    Args:
        args: list of program arguments with configuration options
        tags: queue of tags shared between processes
        lock: lock for locking a shared resource between processes
    """
    hw = SniffleHW(args.serport)

    # Do not follow connections => we're only interested in the advertisements
    hw.cmd_follow(False)

    # Clear preload parameters for encrypted connections
    hw.cmd_interval_preload()

    # Filter by signal strength
    hw.cmd_rssi(args.rssi)

    # Do not filter MACs, hop advertisement channels (37, 38, 39)
    hw.cmd_mac(hop3=True)

    # Disable BT5 extended advertising => not necessary for AirTags
    hw.cmd_auxadv(False)

    # Reset timestamps and flush packet queue
    hw.mark_and_flush()

    while True:
        # Receive message from the Sniffle board
        msg = hw.recv_and_decode()
        # Handle the message accordingly: logging and putting it on the queue
        if isinstance(msg, PacketMessage):
            pkt = DPacketMessage.decode(msg)
            if (
                isinstance(pkt, AdvIndMessage)
                or isinstance(pkt, AdvNonconnIndMessage)
                or isinstance(pkt, AdvScanIndMessage)
                or isinstance(pkt, AdvDirectIndMessage)
            ):
                data: bytes = pkt.body
                if len(data) == 39:
                    # Cut off PDU header if present
                    data = data[2:]
                if data[6:12] == bytes([0x1E, 0xFF, 0x4C, 0x00, 0x12, 0x19]):
                    # Identified as an AirTag -- contains the typical hardcoded identifiers
                    try:
                        tags.put_nowait(data)
                    except queue.Full:
                        lock.acquire()
                        log.warn("Queue full, discarding packet")
                        lock.release()
                elif log.isEnabledFor(logging.DEBUG):
                    lock.acquire()
                    log.debug("Recorded advertisement not originating from an AirTag")
                    lock.release()
        elif (
            isinstance(msg, DebugMessage)
            or isinstance(msg, StateMessage)
            or isinstance(msg, MeasurementMessage)
        ):
            lock.acquire()
            log.debug(msg)
            lock.release()


def api_sender(args, tags, lock):
    """Sends the recorded AirTag advertisements to the server API

    Args:
        args: list of program arguments with configuration options
        tags: queue of tags shared between processes
        lock: lock for locking a shared resource between processes
    """
    with rq.Session() as s:
        s.headers = {"Content-Type": "application/octet-stream"}
        while True:
            data: bytes = tags.get(block=True, timeout=None)
            if log.isEnabledFor(logging.DEBUG):
                lock.acquire()
                log.debug(f"Posting {data} to the server")
                lock.release()
            res = s.post(args.url + "/api/v1/airtag", data=data)
            if not res.status_code == 200:
                lock.acquire()
                log.error(
                    f"Tag could not be sent to the API, error message: {res.text}"
                )
                lock.release()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Sniffer incl. API client for relaying AirTag advertisements via Sniffle"
    )
    parser.add_argument(
        "-s", "--serport", default=None, help="Sniffle serial port name"
    )
    parser.add_argument(
        "-r", "--rssi", default=-128, type=int, help="Filter packets by minimum RSSI"
    )
    parser.add_argument(
        "-u",
        "--url",
        required=True,
        help="Base URL (in <host[:port]> format) of the relayer API",
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
    if not args.url.startswith("http"):
        args.url = "http://" + args.url

    # Set log level based on given verbosity
    verb_levels = [logging.WARNING, logging.INFO, logging.DEBUG]
    log.setLevel(verb_levels[min(len(verb_levels) - 1, args.verbosity)])

    with mp.Manager() as manager:
        tags = manager.Queue()
        lock = manager.Lock()
        receiver = mp.Process(target=ble_receiver, args=(args, tags, lock))
        sender = mp.Process(target=api_sender, args=(args, tags, lock))
        try:
            sender.start()
            receiver.start()
            sender.join()
            receiver.join()
        except KeyboardInterrupt:
            log.info("Received keyboard interrupt, cleaning up and exiting")
            sender.terminate()
            receiver.terminate()
            sender.join()
            receiver.join()
        finally:
            sender.close()
            receiver.close()
