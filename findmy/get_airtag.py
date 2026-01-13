#!/usr/bin/env python3

import logging
import sys
from pathlib import Path
from datetime import datetime, timezone
import json

from _login import get_account_sync

from findmy import KeyPair
from findmy.reports import RemoteAnisetteProvider

# URL to (public or local) anisette server
ANISETTE_SERVER = "http://localhost:6969"

logging.basicConfig(level=logging.DEBUG)


def main(in_path: str, out_path: str) -> int:
    # Read precomputed keys
    with Path(in_path).open("rb") as f:
        keys = json.load(f)

    # Log into an Apple account
    logging.info("Logging into account")
    anisette = RemoteAnisetteProvider(ANISETTE_SERVER)
    acc = get_account_sync(anisette)

    # Fetch reports!
    logging.info("Fetching reports")
    report_set = set()
    for reports in acc.fetch_reports(
        list(map(lambda x: KeyPair.from_b64(x), keys)),
        date_from=datetime(2024, 8, 1, tzinfo=timezone.utc),
        date_to=datetime(2025, 5, 1, tzinfo=timezone.utc),
    ).values():
        report_set.update(reports)

    # Transform reports for dumping
    logging.info("Massaging reports into dicts")
    report_dicts = [
        {
            "timestamp": str(rep.timestamp),
            "published_at": str(rep.published_at),
            "keys": {
                "privkey": rep.key.private_key_b64,
                "pubkey": rep.key.adv_key_b64,
                "pubkey_hash": rep.key.hashed_adv_key_b64,
            },
            "description": rep.description,
            "latitude": rep.latitude,
            "longitude": rep.longitude,
            "confidence": rep.confidence,
            "status": rep.status,
        }
        for rep in sorted(report_set)
    ]

    # Dump the reports to JSON
    logging.info("Dumping reports")
    with Path(out_path).open("w") as f:
        json.dump(report_dicts, f, indent=4)

    return 0


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(
            f"Usage: {sys.argv[0]} <path to json with precomputed keys> <path to json to dump reports to>",
            file=sys.stderr,
        )
        sys.exit(1)

    sys.exit(main(sys.argv[1], sys.argv[2]))
