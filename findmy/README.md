# PrivacyShield - FindMy.py scripts

This directory contains a patch to the upstream FindMy.py project to
significantly speed up location report filtering if many reports are present
and scripts to retrieve and visualize AirTag location reports from Apple's
servers.
Either install the FindMy.py package manually or get the Python wheel to
install via the top-level Makefile (`make findmy-0.7.6-py3-none-any.whl`).

In any case, running the analysis scripts requires extracting the AirTag plist
files from a macOS keychain first.
We recommend checking out
[upstream tutorials]({https://docs.mikealmel.ooo/FindMy.py/getstarted/02-fetching.html)
on how to do this.

## Manual / Editable Install

1. Clone the submodule (`git submodule update --init`) if not already present
2. Apply the patch (`pushd findmypy-upstream; patch -p1 < ../privacyshield.patch; popd`)
3. Install the FindMy.py package in your Python installation (preferably a virtualenv)
   via `pip3 install -e findmypy-upstream` and install the required dependencies via
   `pip3 install -r requirements.txt`
