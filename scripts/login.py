#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class TelethonDeps:
    telegram_client: Any
    string_session: Any
    api_id_invalid_error: type[Exception]
    phone_code_invalid_error: type[Exception]
    phone_number_invalid_error: type[Exception]
    session_password_needed_error: type[Exception]


def load_telethon() -> TelethonDeps:
    try:
        from telethon import TelegramClient
        from telethon.errors import (
            ApiIdInvalidError,
            PhoneCodeInvalidError,
            PhoneNumberInvalidError,
            SessionPasswordNeededError,
        )
        from telethon.sessions import StringSession
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "Telethon is not installed. Run: pip install -e \".[dev]\""
        ) from exc

    return TelethonDeps(
        telegram_client=TelegramClient,
        string_session=StringSession,
        api_id_invalid_error=ApiIdInvalidError,
        phone_code_invalid_error=PhoneCodeInvalidError,
        phone_number_invalid_error=PhoneNumberInvalidError,
        session_password_needed_error=SessionPasswordNeededError,
    )


def load_dotenv(path: str | Path) -> None:
    env_path = Path(path)
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Log in with Telethon locally and print a StringSession "
            "for AWS Secrets Manager."
        )
    )
    parser.add_argument(
        "--api-id",
        type=int,
        default=None,
        help="Telegram API ID from my.telegram.org",
    )
    parser.add_argument("--api-hash", default=None, help="Telegram API hash from my.telegram.org")
    parser.add_argument("--phone", default=None, help="Phone number in international format")
    parser.add_argument(
        "--qr",
        action="store_true",
        help="Log in by scanning a QR code from an already logged-in Telegram app",
    )
    parser.add_argument(
        "--qr-timeout",
        type=float,
        default=60,
        help="Seconds to wait for each QR scan attempt",
    )
    parser.add_argument(
        "--qr-attempts",
        type=int,
        default=3,
        help="How many QR codes to show before giving up",
    )
    parser.add_argument("--env-file", default=".env", help="Path to a local .env file")
    return parser.parse_args()


def read_api_id(value: int | None) -> int:
    if value is not None:
        return value

    env_value = os.getenv("TELEGRAM_API_ID") or os.getenv("telegram_api_id")
    if env_value:
        try:
            return int(env_value)
        except ValueError as exc:
            raise SystemExit("TELEGRAM_API_ID must be an integer") from exc

    raw_value = input("Telegram api_id: ").strip()
    try:
        return int(raw_value)
    except ValueError as exc:
        raise SystemExit("api_id must be an integer") from exc


def read_api_hash(value: str | None) -> str:
    if value:
        return value

    env_value = os.getenv("TELEGRAM_API_HASH") or os.getenv("telegram_api_hash")
    if env_value:
        return env_value

    return getpass.getpass("Telegram api_hash: ").strip()


def print_qr_login_url(url: str) -> None:
    try:
        import qrcode
    except ModuleNotFoundError:
        print(
            "qrcode is not installed, so only the login URL can be shown.",
            file=sys.stderr,
        )
        print("Install dependencies with: pip install -e \".[dev]\"", file=sys.stderr)
        print(f"\nOpen this Telegram login URL on an already logged-in device:\n{url}\n")
        return

    qr = qrcode.QRCode(border=1)
    qr.add_data(url)
    qr.make(fit=True)
    qr.print_ascii(tty=True)
    print(
        "\nScan this QR code with Telegram on a device where the parent account "
        "is already logged in.",
        file=sys.stderr,
    )
    print("Telegram mobile: Settings > Devices > Link Desktop Device.", file=sys.stderr)


async def sign_in_with_qr(client: Any, deps: TelethonDeps, timeout: float, attempts: int) -> None:
    if attempts < 1:
        raise SystemExit("--qr-attempts must be at least 1")
    if timeout <= 0:
        raise SystemExit("--qr-timeout must be greater than 0")

    qr_login = await client.qr_login()
    for attempt in range(1, attempts + 1):
        print(f"\nQR login attempt {attempt}/{attempts}", file=sys.stderr)
        print_qr_login_url(qr_login.url)

        try:
            await qr_login.wait(timeout=timeout)
            return
        except deps.session_password_needed_error:
            password = getpass.getpass("Telegram 2FA password: ")
            await client.sign_in(password=password)
            return
        except asyncio.TimeoutError:
            if attempt >= attempts:
                raise SystemExit("QR login timed out before the code was scanned")
            print("QR code expired or was not scanned; generating a new one.", file=sys.stderr)
            await qr_login.recreate()


async def create_string_session(
    api_id: int,
    api_hash: str,
    phone: str | None,
    use_qr: bool,
    qr_timeout: float,
    qr_attempts: int,
    deps: TelethonDeps,
) -> str:
    client = deps.telegram_client(deps.string_session(), api_id, api_hash)
    await client.connect()

    try:
        if not await client.is_user_authorized():
            if use_qr:
                await sign_in_with_qr(client, deps, qr_timeout, qr_attempts)
            else:
                phone_number = phone or input("Phone number, including country code: ").strip()
                await client.send_code_request(phone_number)
                code = input("Telegram login code: ").strip().replace(" ", "")

                try:
                    await client.sign_in(phone=phone_number, code=code)
                except deps.session_password_needed_error:
                    password = getpass.getpass("Telegram 2FA password: ")
                    await client.sign_in(password=password)

        me = await client.get_me()
        username = f"@{me.username}" if getattr(me, "username", None) else "(no username)"
        print(f"Logged in as {me.id} {username}", file=sys.stderr)
        return client.session.save()
    finally:
        await client.disconnect()


async def async_main() -> int:
    args = parse_args()
    load_dotenv(args.env_file)

    api_id = read_api_id(args.api_id)
    api_hash = read_api_hash(args.api_hash)
    if not api_hash:
        raise SystemExit("api_hash is required")

    deps = load_telethon()

    try:
        session = await create_string_session(
            api_id,
            api_hash,
            args.phone,
            args.qr,
            args.qr_timeout,
            args.qr_attempts,
            deps,
        )
    except deps.api_id_invalid_error as exc:
        raise SystemExit("Telegram rejected the api_id/api_hash pair") from exc
    except deps.phone_number_invalid_error as exc:
        raise SystemExit("Telegram rejected the phone number") from exc
    except deps.phone_code_invalid_error as exc:
        raise SystemExit("Telegram rejected the login code") from exc

    print("\nTelethon StringSession:")
    print(session)
    print(
        "\nStore this exact value as telethon_string_session in AWS Secrets Manager. "
        "Do not commit it or paste it into logs.",
        file=sys.stderr,
    )
    return 0


def main() -> int:
    return asyncio.run(async_main())


if __name__ == "__main__":
    raise SystemExit(main())
