# PrivacyShield - AirGuard Application

1. Clone the submodule (`git submodule update --init`) if not already present
2. Apply the patch (`pushd airguard-upstream; patch -p1 < ../privacyshield.patch; popd`)
3. Build the AirGuard application according to the upstream instructions
