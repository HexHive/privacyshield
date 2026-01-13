# PrivacyShield - FindMy.py scripts

1. Clone the submodule (`git submodule update --init`) if not already present
2. Apply the patch (`pushd findmypy-upstream; patch -p1 < ../privacyshield.patch; popd`)
3. Install the FindMy.py package in your Python installation (preferably a virtualenv)
   via `pip3 install -e findmypy-upstream` and install the required dependencies via
   `pip3 install -r requirements.txt`
4. Run the scripts for further analysis (require extracting the AirTag plist files
   from a macOS keychain first!)
