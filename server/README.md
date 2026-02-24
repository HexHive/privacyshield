# PrivacyShield Relay Server

This Flask application constitutes the relay server component that receives
AirTag beacons from clients and re-transmits them to relay stations that
request them from the server.

You can launch the server by installing the necessary requirements
(`pip3 install -r server/requirements.txt`), ideally in a Python virtualenv,
and then running `python3 server/server.py`.
