# PrivacyShield: Relaying BLE Beacons to Counter Unsolicited Tracking

This repository contains the code for our USENIX Security '26 paper
"PrivacyShield: Relaying BLE Beacons to Counter Unsolicited Tracking".
We will add a link to the paper once it is available online.

The repository contains our current server and relay implementation based on a
Python Flask app (subdirectory [`./server`](./server)), a customized version of
the AirGuard app (subdirectory [`./airguard`](./airguard)), and our custom
ESP32 relay firmware (subdirectory [`./relay-fw`](./relay-fw)).

It also contains code based on the Sniffle BLE sniffer (subdirectory
[`./sniffle`](./sniffle).
This code is not actively used anymore but was originally used for some
experimentation and is kept in the repository for completeness' sake.

Furthermore, the repository contains scripts to retrieve and visualize AirTag
location reports from Apple's servers via
[FindMy.py](https://github.com/malmeloo/FindMy.py).
These scripts are not required for the functionality of PrivacyShield but are
useful for debugging the system or generally get more introspection into the
system.

## How to Use

Run the server executable on a server that is reachable from your sniffers and
relayers.
You can launch the server by installing the necessary requirements
(`pip3 install -r server/requirements.txt`), ideally in a Python virtualenv,
and then running `python3 server/server.py`.

Update the relay-firmware configuration to add the server endpoint (e.g., by
running `make sh` in the relay-fw subdirectory and then configuring the
firmware via `idf.py menuconfig`).
Build and flash the firmware to an ESP32 dev board via `make build` and
`make flash` (or just `make flash`, this implies building).

Build the AirGuard app for recording and reporting BLE beacons according to
the project's instructions and run it on an Android phone.

The AirGuard app should now report AirTag beacons to the server, from where
one or multiple relays regularly fetch new advertisements and relay them.
Confirm in your Find My application on iOS or macOS that the AirTag now shows
up at the relayed location.

## License

This project is double-licensed under the GPLv3, and MIT licenses, depending on
the component.

The [sniffle](./sniffle) project is licensed under [GPLv3](./sniffle/LICENSE).
We adhere to this license and state all changes we made to the project, namely:

* Addition of a [Dockerfile](./sniffle/Dockerfile) which sets up a build
  environment for the sniffle firmware, and
* Addition of a [compose.yaml](./sniffle/compose.yaml) which allows
  starting a container based on the above build image with the correct
  parameters.
* Addition of an argument to
  [sniff_receiver.py](./sniffle/python_cli/sniff_receiver.py) that allows to
  forward recorded data via UDP.
* Addition of the [sniffer.py](./sniffle/python_cli/sniffer.py) and
  [relayer.py](./sniffle/python_cli/relayer.py) scripts that we used in our
  experiments.

The remainder of the project is licensed under the [MIT license](./LICENSE).

In case you're not sure which license applies to a file, check the top of the
file for license information.
If the file does not contain a license header, just traverse the directory tree
upwards from the file's location.
The first `LICENSE` file you encounter contains the license that applies to the
file.
