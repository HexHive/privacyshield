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

### Relay Server

Run the relay server application on a server that is reachable from both your
clients and the relays.
You can simply start the server with the given Makefile via `make run-server`.
Make sure to take note of the server's URL (the domain if you've set up DNS
entries or otherwise the IP), including the port used.
You will need this URL for configuring the client application and relay
firmware.

### Relay Firmware

Note: our Makefile by default assumes that you are using Podman instead of
Docker. If you prefer to use Docker, you will need to remove the
`--group-add=keep-groups` from the [Makefile](./relay-fw/Makefile), as Docker
does not support this option.

Update the relay-firmware configuration to add the server endpoint and WiFi
credentials.
You can either add the corresponding config values directly to the
`sdkconfig.defaults` file (set `CONFIG_RELAY_ENDPOINT_HOST` to your server's
host name or IP and `CONFIG_RELAY_ENDPOINT_PORT` to the port it's listening on)
or use the ESP-IDF menuconfig interface.
We recommend the latter, as it's significantly easier.
Do so by running `make sh` in the relay-fw subdirectory and then configuring
the firmware via `idf.py menuconfig`.
In the menu, navigate to the "Relay FW Configuration" submenu and configure the
server URL and WiFi credentials there.

Then, build and flash the firmware to an ESP32 dev board via `make build` and
`make flash` (or just `make flash`, this implies building).
Once you configured the firmware, you can also build it from the top-level
Makefile via `make relay-fw.bin` but you'd need to flash it manually then.
If you don't use our Makefile target to flash the firmware, you can also flash
it manually via esptool, e.g., by running

```bash
python3 -m esptool \
    --chip esp32c3 -p /dev/<serial port device here> -b 460800 \
    --before default_reset --after hard_reset \
    write_flash --flash_mode dio --flash_size detect --flash_freq 80m \
    0x0 bootloader.bin 0x8000 partition-table.bin 0x10000 relay-fw.bin
```

### Client Application

Build the AirGuard app for recording and reporting BLE beacons according to
the project's instructions and run it on an Android phone.
First, adjust the `psURL` variable in
[the patch file](./airguard/privacyshield.patch) to point to your server URL.
Then, you can build the app via `make airguard.apk` and install it on your
phone.
The AirGuard app should then report AirTag beacons to the server, from where
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
