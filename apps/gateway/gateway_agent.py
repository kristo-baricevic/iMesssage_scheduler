import os
import time
import json
import subprocess
from dataclasses import dataclass
from typing import Optional

import requests
from dotenv import load_dotenv

APPLE_SCRIPT = r'''
on run argv
  set theHandle to item 1 of argv
  set theMessage to item 2 of argv

  tell application "Messages"
    set targetService to 1st service whose service type is iMessage
    set targetBuddy to buddy theHandle of targetService
    send theMessage to targetBuddy
  end tell
end run
'''

@dataclass(frozen=True)
class ClaimedMessage:
    id: str
    to_handle: str
    body: str
    scheduled_for: str


def send_imessage(*, to_handle: str, body: str) -> None:
    proc = subprocess.run(
        ["osascript", "-e", APPLE_SCRIPT, to_handle, body],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "osascript failed").strip())


def claim_next(*, api_base_url: str, gateway_id: str) -> Optional[ClaimedMessage]:
    url = f"{api_base_url.rstrip('/')}/api/gateway/claim/"
    res = requests.post(url, json={"gateway_id": gateway_id}, timeout=10)

    if res.status_code == 204:
        return None
    res.raise_for_status()

    data = res.json()
    return ClaimedMessage(
        id=data["id"],
        to_handle=data["to_handle"],
        body=data["body"],
        scheduled_for=data["scheduled_for"],
    )


def report_status(
    *,
    api_base_url: str,
    message_id: str,
    status: str,
    error: Optional[str] = None,
    detail: Optional[dict] = None,
) -> None:
    url = f"{api_base_url.rstrip('/')}/api/gateway/report/"
    payload = {
        "message_id": message_id,
        "status": status,
        "error": error,
        "detail": detail or None,
    }
    res = requests.post(url, json=payload, timeout=10)
    res.raise_for_status()


def main() -> None:
    load_dotenv()

    api_base_url = os.environ.get("API_BASE_URL", "http://127.0.0.1:8000")
    gateway_id = os.environ.get("GATEWAY_ID", "mac-1")
    poll_seconds = int(os.environ.get("POLL_SECONDS", "5"))

    print(f"gateway_id={gateway_id} api={api_base_url} poll={poll_seconds}s")

    while True:
        try:
            claimed = claim_next(api_base_url=api_base_url, gateway_id=gateway_id)
            if not claimed:
                time.sleep(poll_seconds)
                continue

            print(f"CLAIMED id={claimed.id} to={claimed.to_handle}")

            try:
                send_imessage(to_handle=claimed.to_handle, body=claimed.body)
                report_status(
                    api_base_url=api_base_url,
                    message_id=claimed.id,
                    status="SENT",
                    detail={"gateway_id": gateway_id},
                )
                print(f"SENT id={claimed.id}")
            except Exception as send_err:
                report_status(
                    api_base_url=api_base_url,
                    message_id=claimed.id,
                    status="FAILED",
                    error=str(send_err),
                    detail={"gateway_id": gateway_id},
                )
                print(f"FAILED id={claimed.id} err={send_err}")

        except Exception as loop_err:
            print(f"LOOP_ERROR {loop_err}")
            time.sleep(poll_seconds)


if __name__ == "__main__":
    main()
