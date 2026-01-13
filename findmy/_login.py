import json
from pathlib import Path

from findmy.reports import (
    AppleAccount,
    BaseAnisetteProvider,
    LoginState,
    SmsSecondFactorMethod,
    TrustedDeviceSecondFactorMethod,
)

ACCOUNT_STORE = "account.json"


def _login_sync(account: AppleAccount) -> None:
    email = input("email?  > ")
    password = input("passwd? > ")

    state = account.login(email, password)

    if state == LoginState.REQUIRE_2FA:  # Account requires 2FA
        # This only supports SMS methods for now
        methods = account.get_2fa_methods()

        # Print the (masked) phone numbers
        for i, method in enumerate(methods):
            if isinstance(method, TrustedDeviceSecondFactorMethod):
                print(f"{i} - Trusted Device")
            elif isinstance(method, SmsSecondFactorMethod):
                print(f"{i} - SMS ({method.phone_number})")

        ind = int(input("Method? > "))

        method = methods[ind]
        method.request()
        code = input("Code? > ")

        # This automatically finishes the post-2FA login flow
        method.submit(code)


def get_account_sync(anisette: BaseAnisetteProvider) -> AppleAccount:
    """Tries to restore a saved Apple account, or prompts the user for login otherwise. (sync)"""
    acc = AppleAccount(anisette)

    # Save / restore account logic
    acc_store = Path("account.json")
    try:
        with acc_store.open() as f:
            acc.restore(json.load(f))
    except FileNotFoundError:
        _login_sync(acc)
        with acc_store.open("w+") as f:
            json.dump(acc.export(), f)

    return acc
