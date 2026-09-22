#!/usr/bin/env python3
"""Cài YOLOv8n + ultralytics trên Jetson, bật AI thật, restart eo-service.

  py -3 scripts/setup-jetson-ai.py
  py -3 scripts/setup-jetson-ai.py --host 192.168.1.16 --user thanh

Cần mạng trên Jetson để pip + tải yolov8n.pt.
Mật khẩu: JETSON_PASSWORD hoặc nhập khi chạy.
"""
from __future__ import annotations

import argparse
import getpass
import os
import sys
import time

try:
    import paramiko
except ImportError:
    print("Cần paramiko: py -3 -m pip install paramiko", file=sys.stderr)
    raise SystemExit(1)

REMOTE_DEFAULT = "/home/thanh/eo-control/jetson-service"


def safe(s: str) -> str:
    return s.encode(sys.stdout.encoding or "utf-8", "replace").decode(sys.stdout.encoding or "utf-8", "replace")


def connect(host: str, user: str, password: str | None) -> paramiko.SSHClient:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    kwargs: dict = {"hostname": host, "username": user, "timeout": 25}
    if password:
        kwargs.update(password=password, allow_agent=False, look_for_keys=False)
    else:
        kwargs.update(allow_agent=True, look_for_keys=True)
    client.connect(**kwargs)
    return client


def run(client: paramiko.SSHClient, cmd: str, timeout: int = 900, password: str | None = None) -> tuple[int, str]:
    if password and cmd.strip().startswith("sudo "):
        cmd = f"echo {password} | sudo -S " + cmd[5:]
    print(f"$ {cmd[:200]}")
    _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    code = stdout.channel.recv_exit_status()
    text = (out + err).strip()
    if text:
        print(safe(text[-3000:]))
    return code, text


def main() -> int:
    p = argparse.ArgumentParser(description="Setup YOLOv8n AI on Jetson")
    p.add_argument("--host", default=os.environ.get("JETSON_HOST", "192.168.1.16"))
    p.add_argument("--user", default=os.environ.get("JETSON_USER", "thanh"))
    p.add_argument("--remote", default=os.environ.get("JETSON_REMOTE", REMOTE_DEFAULT))
    args = p.parse_args()

    password = os.environ.get("JETSON_PASSWORD")
    try:
        if password:
            client = connect(args.host, args.user, password)
        else:
            try:
                client = connect(args.host, args.user, None)
            except Exception:
                password = getpass.getpass(f"Password cho {args.user}@{args.host}: ")
                client = connect(args.host, args.user, password)
    except Exception as exc:
        print(f"Không kết nối được {args.user}@{args.host}: {exc}", file=sys.stderr)
        print("Bật Jetson / kiểm tra LAN rồi chạy lại.", file=sys.stderr)
        return 2

    remote = args.remote
    try:
        code, _ = run(client, f"test -x {remote}/.venv/bin/python && echo VENV_OK")
        if code != 0:
            print("Không thấy .venv trên Jetson — chạy deploy-jetson.py trước.", file=sys.stderr)
            return 1

        # ultralytics (+ deps). Torch CUDA trên JetPack có thể đã có sẵn.
        code, _ = run(
            client,
            f"cd {remote} && .venv/bin/pip install -r requirements-jetson.txt",
            timeout=1200,
        )
        if code != 0:
            print("pip requirements-jetson.txt thất bại.", file=sys.stderr)
            return code

        # Tải weights vào working directory service
        code, _ = run(
            client,
            f"cd {remote} && .venv/bin/python -c \"from ultralytics import YOLO; m=YOLO('yolov8n.pt'); print('MODEL', m.ckpt_path if hasattr(m,'ckpt_path') else 'yolov8n.pt')\"",
            timeout=600,
        )
        if code != 0:
            print("Tải/load yolov8n.pt thất bại.", file=sys.stderr)
            return code

        # Đảm bảo config: sim false + AI YOLO
        patch = r"""
import re, pathlib
p = pathlib.Path('""" + remote + r"""/config.yaml')
t = p.read_text(encoding='utf-8')
t2 = re.sub(r'(?m)^sim:\s*\S+', 'sim: false', t, count=1)
if 'ai:' in t2:
    t2 = re.sub(r'(?m)^(\s*)model:\s*.*$', r'\1model: yolov8n.pt', t2, count=1)
    t2 = re.sub(r'(?m)^(\s*)use_ultralytics:\s*.*$', r'\1use_ultralytics: true', t2, count=1)
else:
    t2 += '\nai:\n  model: yolov8n.pt\n  device: 0\n  conf: 0.4\n  imgsz: 640\n  classes: [0, 1, 2, 3, 5, 7]\n  use_ultralytics: true\n'
p.write_text(t2, encoding='utf-8')
print('config patched')
print(p.read_text(encoding='utf-8').split('ai:')[-1][:400] if 'ai:' in t2 else 'no ai')
"""
        run(client, f"{remote}/.venv/bin/python - <<'PY'\n{patch}\nPY")

        # Unit không dùng --sim
        unit = f"""[Unit]
Description=EO Control Jetson Service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User={args.user}
WorkingDirectory={remote}
ExecStart={remote}/.venv/bin/python -m eos_service --config {remote}/config.yaml --host 0.0.0.0 --port 8765
Restart=on-failure
RestartSec=3
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
"""
        run(client, f"cat > /tmp/eo-service.service << 'EOF'\n{unit}EOF")
        run(client, "sudo cp /tmp/eo-service.service /etc/systemd/system/eo-service.service", password=password)
        run(client, "sudo systemctl daemon-reload", password=password)
        run(client, "sudo systemctl restart eo-service", password=password)
        time.sleep(4)
        run(client, "sudo systemctl is-active eo-service", password=password)
        run(client, "curl -s http://127.0.0.1:8765/health || true")
        run(client, "sudo journalctl -u eo-service -n 40 --no-pager", password=password)
        run(client, f"cd {remote} && .venv/bin/python -m eos_service.hw_test --config {remote}/config.yaml ai", timeout=180)

        print("Xong — YOLOv8n sẵn sàng trên Jetson.")
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
