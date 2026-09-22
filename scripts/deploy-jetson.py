#!/usr/bin/env python3
"""Đồng bộ jetson-service lên Jetson rồi restart eo-service.

Cách dùng (từ thư mục gốc repo):

  py -3 scripts/deploy-jetson.py
  py -3 scripts/deploy-jetson.py --host 192.168.1.16 --user thanh
  py -3 scripts/deploy-jetson.py --deps          # pip install requirements-jetson.txt
  py -3 scripts/deploy-jetson.py --ai            # deps + tải yolov8n.pt + sim:false
  py -3 scripts/deploy-jetson.py --include-config  # ghi đè cả config.yaml

Mật khẩu: biến môi trường JETSON_PASSWORD, hoặc nhập khi chạy.
Khuyến nghị: cấu hình SSH key để khỏi nhập mật khẩu.
"""
from __future__ import annotations

import argparse
import getpass
import os
import posixpath
import sys
import time
from pathlib import Path

try:
    import paramiko
except ImportError:
    print("Cần paramiko: py -3 -m pip install paramiko", file=sys.stderr)
    raise SystemExit(1)

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / "jetson-service"
REMOTE_DEFAULT = "/home/thanh/eo-control/jetson-service"
SKIP_DIRS = {".venv", "__pycache__", ".git", "data"}
SKIP_SUFFIX = {".pyc", ".pt", ".engine"}
# Không ghi đè config trên Jetson trừ khi --include-config
SKIP_FILES_DEFAULT = {"config.yaml"}


def safe(s: str) -> str:
    return s.encode(sys.stdout.encoding or "utf-8", "replace").decode(sys.stdout.encoding or "utf-8", "replace")


def connect(host: str, user: str, password: str | None) -> paramiko.SSHClient:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    kwargs = {"hostname": host, "username": user, "timeout": 25}
    if password:
        kwargs.update(password=password, allow_agent=False, look_for_keys=False)
    else:
        kwargs.update(allow_agent=True, look_for_keys=True)
    client.connect(**kwargs)
    return client


def run(client: paramiko.SSHClient, cmd: str, timeout: int = 600, password: str | None = None) -> int:
    if password and cmd.strip().startswith("sudo "):
        cmd = f"echo {password} | sudo -S " + cmd[5:]
    print(f"$ {cmd[:180]}")
    _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    code = stdout.channel.recv_exit_status()
    text = (out + err).strip()
    if text:
        print(safe(text[-2500:]))
    return code


def sftp_mkdirs(sftp: paramiko.SFTPClient, remote: str) -> None:
    parts = [p for p in remote.strip("/").split("/") if p]
    cur = ""
    for p in parts:
        cur += "/" + p
        try:
            sftp.stat(cur)
        except FileNotFoundError:
            sftp.mkdir(cur)


def upload(sftp: paramiko.SFTPClient, local: Path, remote: str, skip_files: set[str]) -> int:
    n = 0
    for root, dirs, files in os.walk(local):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        rel = Path(root).relative_to(local).as_posix()
        rdir = remote if rel == "." else posixpath.join(remote, rel)
        sftp_mkdirs(sftp, rdir)
        for name in files:
            if name in skip_files:
                print(f"  skip {name}")
                continue
            if any(name.endswith(suf) for suf in SKIP_SUFFIX):
                continue
            lp = Path(root) / name
            rp = posixpath.join(rdir, name)
            sftp.put(str(lp), rp)
            n += 1
            print(f"  put {lp.relative_to(local).as_posix()}")
    return n


def main() -> int:
    p = argparse.ArgumentParser(description="Update EO service code on Jetson")
    p.add_argument("--host", default=os.environ.get("JETSON_HOST", "192.168.1.16"))
    p.add_argument("--user", default=os.environ.get("JETSON_USER", "thanh"))
    p.add_argument("--remote", default=os.environ.get("JETSON_REMOTE", REMOTE_DEFAULT))
    p.add_argument("--include-config", action="store_true", help="Ghi đè config.yaml trên Jetson")
    p.add_argument("--deps", action="store_true", help="pip install -r requirements-jetson.txt (gồm ultralytics)")
    p.add_argument("--ai", action="store_true", help="Cài AI deps + tải yolov8n.pt + đảm bảo sim:false rồi restart")
    p.add_argument("--no-restart", action="store_true")
    p.add_argument("--sim", action="store_true", help="Chạy service với --sim (cập nhật unit)")
    args = p.parse_args()

    if not LOCAL.is_dir():
        print(f"Không thấy {LOCAL}", file=sys.stderr)
        return 1

    password = os.environ.get("JETSON_PASSWORD")
    if not password:
        # Thử SSH key trước; nếu fail mới hỏi mật khẩu
        try:
            client = connect(args.host, args.user, None)
        except Exception:
            password = getpass.getpass(f"Password cho {args.user}@{args.host}: ")
            client = connect(args.host, args.user, password)
    else:
        client = connect(args.host, args.user, password)

    try:
        skip = set() if args.include_config else set(SKIP_FILES_DEFAULT)
        run(client, f"mkdir -p {args.remote}")
        sftp = client.open_sftp()
        try:
            n = upload(sftp, LOCAL, args.remote, skip)
        finally:
            sftp.close()
        print(f"Đã upload {n} file → {args.user}@{args.host}:{args.remote}")

        if args.deps or args.ai:
            code = run(client, f"cd {args.remote} && .venv/bin/pip install -r requirements-jetson.txt", timeout=1200)
            if code != 0:
                return code

        if args.ai:
            code = run(
                client,
                f"cd {args.remote} && .venv/bin/python -c \"from ultralytics import YOLO; YOLO('yolov8n.pt'); print('yolov8n.pt OK')\"",
                timeout=600,
            )
            if code != 0:
                return code
            # sim: false + model path
            run(
                client,
                f"cd {args.remote} && .venv/bin/python - <<'PY'\n"
                "import re, pathlib\n"
                "p=pathlib.Path('config.yaml')\n"
                "t=p.read_text(encoding='utf-8')\n"
                "t=re.sub(r'(?m)^sim:\\s*\\S+', 'sim: false', t, count=1)\n"
                "t=re.sub(r'(?m)^(\\s*)model:\\s*.*$', r'\\1model: yolov8n.pt', t, count=1)\n"
                "t=re.sub(r'(?m)^(\\s*)use_ultralytics:\\s*.*$', r'\\1use_ultralytics: true', t, count=1)\n"
                "p.write_text(t, encoding='utf-8')\n"
                "print('config AI ok')\n"
                "PY",
            )

        if args.sim:
            unit = f"""[Unit]
Description=EO Control Jetson Service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User={args.user}
WorkingDirectory={args.remote}
ExecStart={args.remote}/.venv/bin/python -m eos_service --sim --host 0.0.0.0 --port 8765
Restart=on-failure
RestartSec=3
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
"""
            run(client, f"cat > /tmp/eo-service.service << 'EOF'\n{unit}EOF")
            run(client, "sudo cp /tmp/eo-service.service /etc/systemd/system/eo-service.service", password=password)
            run(client, "sudo systemctl daemon-reload", password=password)

        if not args.no_restart:
            run(client, "sudo systemctl restart eo-service", password=password)
            time.sleep(3)
            run(client, "sudo systemctl is-active eo-service", password=password)
            run(client, "curl -s http://127.0.0.1:8765/health || true")
            if args.ai:
                run(client, "sudo journalctl -u eo-service -n 30 --no-pager | grep -E '\\[ai\\]|Error|Traceback' || true", password=password)
                run(client, f"cd {args.remote} && .venv/bin/python -m eos_service.hw_test --config {args.remote}/config.yaml ai", timeout=180)

        print("Xong.")
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
