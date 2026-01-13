#!/usr/bin/env python3

import json
import sys
from pathlib import Path
from datetime import datetime, timezone

from findmy import FindMyAccessory, KeyPair


def main(plist_path: str, json_path: str) -> int:
    with Path(plist_path).open("rb") as f:
        airtag = FindMyAccessory.from_plist(f)

    keys = list(
        map(
            lambda x: x.private_key_b64,
            airtag.keys_between(
                start=datetime(2024, 1, 1, tzinfo=timezone.utc),
                end=datetime(2026, 1, 1, tzinfo=timezone.utc),
            ),
        )
    )

    with Path(json_path).open("w") as f:
        json.dump(keys, f)

    return 0


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(
            f"Usage: {sys.argv[0]} <path to accessory plist> <path to key json>",
            file=sys.stderr,
        )
        print(file=sys.stderr)
        print(
            "The plist file should be dumped from MacOS's FindMy app.", file=sys.stderr
        )
        sys.exit(1)

    sys.exit(main(sys.argv[1], sys.argv[2]))
