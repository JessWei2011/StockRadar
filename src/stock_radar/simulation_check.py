"""Read-only Shioaji simulation login check for Phase 0."""

from __future__ import annotations

import shioaji as sj

from .config import load_settings


def main() -> int:
    try:
        settings = load_settings()
    except RuntimeError as error:
        print("SIMULATION_LOGIN_FAILED=CONFIGURATION_ERROR")
        print(f"ACTION={error}")
        return 3

    api = sj.Shioaji(simulation=True)
    authenticated = False
    try:
        accounts = api.login(
            api_key=settings.api_key,
            secret_key=settings.secret_key,
            subscribe_trade=False,
        )
        authenticated = True
        print("SIMULATION_LOGIN_OK")
        print(f"ACCOUNT_COUNT={len(accounts)}")
        print("TRADE_SUBSCRIPTION=DISABLED")
        return 0
    except sj.BadRequestError:
        print("SIMULATION_LOGIN_FAILED=API_ACCESS_REJECTED")
        print("ACTION=Check the API Key IP allowlist and read-only permissions.")
        return 2
    except Exception as error:
        print(f"SIMULATION_LOGIN_FAILED={type(error).__name__}")
        print("ACTION=Review API Key activation, account permissions, and network connectivity.")
        return 4
    finally:
        if authenticated:
            api.logout()


if __name__ == "__main__":
    raise SystemExit(main())
