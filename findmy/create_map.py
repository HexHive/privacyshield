#!/usr/bin/env python3

import logging
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
from collections import defaultdict, Counter
import json
import folium


logging.basicConfig(level=logging.DEBUG)


def main(in_path: str, out_path: str) -> int:
    # Read location reports
    with Path(in_path).open("rb") as f:
        reports = json.load(f)
    # JSON format (rep = report object):
    # [
    #    {
    #        "timestamp": str(rep.timestamp),
    #        "published_at": str(rep.published_at),
    #        "keys": {
    #            "privkey": rep.key.private_key_b64,
    #            "pubkey": rep.key.adv_key_b64,
    #            "pubkey_hash": rep.key.hashed_adv_key_b64,
    #        },
    #        "description": rep.description,
    #        "latitude": rep.latitude,
    #        "longitude": rep.longitude,
    #        "confidence": rep.confidence,
    #        "status": rep.status,
    #    },
    #    ...
    # ]

    # Create reports to show (only last known for a location)
    logging.info("Create dict of reports")
    cet = timezone(timedelta(hours=1))
    # Reports from...
    min_date = datetime(year=2025, month=2, day=28, hour=12, minute=0, tzinfo=cet)
    # Reports to...
    max_date = datetime(year=2025, month=4, day=1, hour=0, minute=0, tzinfo=cet)
    # Round coordinates to decimal places
    decimals = 4
    report_dict = defaultdict(lambda: min_date)
    report_counter = Counter()
    confidence_sum = defaultdict(int)
    for r in reports:
        key = (round(r["latitude"], decimals), round(r["longitude"], decimals))
        if min_date < (x := datetime.fromisoformat(r["timestamp"])) < max_date:
            report_dict[key] = max(report_dict[key], x)
            report_counter[key] += 1
            confidence_sum[key] += r["confidence"]

    # Dump aggregation information
    logging.info(f"Counts: {report_counter}")
    avg_confidence = {
        k: float(confidence_sum[k]) / float(report_counter[k])
        for k in report_dict.keys()
    }
    logging.info(f"Average confidence: {avg_confidence}")

    # Create map
    logging.info("Create map")
    m = folium.Map(location=[46.52868, 6.57583], zoom_start=15)
    for k, v in report_dict.items():
        folium.Marker(
            location=k,
            popup=f"{report_counter[k]} report(s) registered at {k[0]}/{k[1]}, last at {v}, "
            + f"average confidence score: {avg_confidence[k]}",
        ).add_to(m)

    logging.info("Save map")
    m.save(out_path)

    return 0


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(
            f"Usage: {sys.argv[0]} <path to json with precomputed keys> <path to html to dump map to>",
            file=sys.stderr,
        )
        sys.exit(1)

    sys.exit(main(sys.argv[1], sys.argv[2]))
