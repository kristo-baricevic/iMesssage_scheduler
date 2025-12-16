from __future__ import annotations

import json
import os
import select
import stat
import subprocess
import tempfile
import time
from pathlib import Path


def _repo_root() -> Path:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=Path(__file__).resolve().parent,
            stderr=subprocess.STDOUT,
        )
        return Path(out.decode("utf-8", errors="replace").strip())
    except Exception:
        return Path(__file__).resolve().parents[3]


REPO_ROOT = _repo_root()
COMPOSE_DIR = REPO_ROOT / "infrastructure"
GATEWAY_SCRIPT = REPO_ROOT / "apps" / "gateway" / "gateway_agent.py"

API_BASE_URL = os.environ.get("API_BASE_URL", "http://127.0.0.1:8000")
GATEWAY_ID = os.environ.get("GATEWAY_ID", "mac-1")
KEEP_STACK = os.environ.get("KEEP_STACK", "0") == "1"


def run_stream(cmd: list[str], *, cwd: Path | None = None, timeout: int = 900) -> None:
    print("+", " ".join(cmd))
    subprocess.run(cmd, cwd=str(cwd) if cwd else None, timeout=timeout, check=True)


def run_capture(cmd: list[str], *, cwd: Path | None = None, timeout: int = 120) -> str:
    cmd = [c.replace("\x00", "") for c in cmd]
    proc = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
        check=False,
    )
    out = (proc.stdout or b"").decode("utf-8", errors="replace")
    if proc.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\n\n{out}")
    return out


def extract_last_json_object(out: str) -> dict:
    decoder = json.JSONDecoder()
    for i in range(len(out) - 1, -1, -1):
        if out[i] != "{":
            continue
        try:
            obj, _ = decoder.raw_decode(out[i:])
            if isinstance(obj, dict):
                return obj
        except Exception:
            continue
    raise RuntimeError(f"Expected JSON object in output, got:\n{out}")


def shell_json(py: str) -> dict:
    out = run_capture(
        ["docker", "compose", "exec", "-T", "api", "python3", "manage.py", "shell", "-c", py],
        cwd=COMPOSE_DIR,
    )
    return extract_last_json_object(out)


def drain_gateway_stdout(proc: subprocess.Popen[bytes]) -> None:
    if proc.stdout is None:
        return
    while True:
        r, _, _ = select.select([proc.stdout], [], [], 0)
        if not r:
            return
        line = proc.stdout.readline()
        if not line:
            return
        print("[gateway]", line.decode("utf-8", errors="replace").rstrip())


def main() -> int:
    if not COMPOSE_DIR.exists():
        raise RuntimeError(f"Expected compose dir at {COMPOSE_DIR}")
    if not GATEWAY_SCRIPT.exists():
        raise RuntimeError(f"Expected gateway script at {GATEWAY_SCRIPT}")

    run_stream(["docker", "compose", "up", "-d", "--build"], cwd=COMPOSE_DIR)

    gateway_proc: subprocess.Popen[bytes] | None = None

    try:
        run_stream(
            ["docker", "compose", "exec", "-T", "api", "python3", "manage.py", "migrate"],
            cwd=COMPOSE_DIR,
            timeout=600,
        )

        shell_json(
            "import json; "
            "from django.utils import timezone; "
            "from scheduler.models import DeliveryThrottle; "
            "DeliveryThrottle.objects.update_or_create("
            "id=1, defaults={'interval_seconds': 0, 'next_send_at': timezone.now()}"
            "); "
            "print(json.dumps({'ok': True}))"
        )

        created = shell_json(
            "import json; "
            "from django.utils import timezone; "
            "from datetime import timedelta; "
            "from scheduler.models import ScheduledMessage, MessageStatus; "
            "m = ScheduledMessage.objects.create("
            "to_handle='+15551234567', "
            "body='Hello! How are you? This is a message from the e2e unit test.', "
            "scheduled_for=timezone.now()-timedelta(seconds=1), "
            "status=MessageStatus.QUEUED, "
            "claimed_at=None, "
            "claimed_by=None, "
            "attempt_count=0"
            "); "
            "print(json.dumps({'id': str(m.id)}))"
        )
        msg_id = created["id"]

        tick_res = shell_json(
            "import json; "
            "from scheduler.tasks import scheduler_tick; "
            "print(json.dumps(scheduler_tick()))"
        )
        print("scheduler_tick:", tick_res)

        fakebin = Path(tempfile.mkdtemp(prefix="fake_osascript_"))
        fake_osascript = fakebin / "osascript"
        fake_osascript.write_text("#!/bin/sh\nexit 0\n")
        fake_osascript.chmod(fake_osascript.stat().st_mode | stat.S_IEXEC)

        env = os.environ.copy()
        env["API_BASE_URL"] = API_BASE_URL
        env["GATEWAY_ID"] = GATEWAY_ID
        env["POLL_SECONDS"] = "1"
        env["PATH"] = f"{fakebin}{os.pathsep}{env.get('PATH','')}"

        print(f"Starting gateway script: {GATEWAY_SCRIPT}")
        gateway_proc = subprocess.Popen(
            ["python3", str(GATEWAY_SCRIPT)],
            cwd=str(REPO_ROOT),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )

        deadline = time.time() + 40
        while time.time() < deadline:
            if gateway_proc.poll() is not None:
                drain_gateway_stdout(gateway_proc)
                raise RuntimeError(f"Gateway exited with code {gateway_proc.returncode}")

            drain_gateway_stdout(gateway_proc)

            row = shell_json(
                "import json; "
                "from scheduler.models import ScheduledMessage; "
                f"m = ScheduledMessage.objects.get(id='{msg_id}'); "
                "print(json.dumps({"
                "'status': m.status, "
                "'claimed_by': m.claimed_by, "
                "'claimed_at': (m.claimed_at.isoformat() if m.claimed_at else None), "
                "'attempt_count': m.attempt_count"
                "}))"
            )
            print("db:", row)

            if row["status"] == "SENT":
                print(f"OK message_id={msg_id} status=SENT")
                return 0

            time.sleep(1)

        raise RuntimeError(f"Message {msg_id} never reached SENT")

    finally:
        if gateway_proc is not None:
            try:
                drain_gateway_stdout(gateway_proc)
            except Exception:
                pass
            try:
                gateway_proc.terminate()
                gateway_proc.wait(timeout=5)
            except Exception:
                try:
                    gateway_proc.kill()
                except Exception:
                    pass

        if KEEP_STACK:
            print("KEEP_STACK=1 set, leaving docker compose stack running for inspection.")
        else:
            run_stream(["docker", "compose", "down", "-v", "--remove-orphans"], cwd=COMPOSE_DIR, timeout=300)

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
