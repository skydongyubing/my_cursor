"""Gitee 在线升级：启动检查 manifest → 下载新 exe → sha256 校验 → 替换重启。

manifest（latest.json）放在 Gitee 仓库 raw 地址，格式：

    {
        "version": "1.5",
        "url": "https://gitee.com/<owner>/<repo>/releases/download/v1.5/威宇佳烧录1.5.exe",
        "sha256": "<新 exe 的 sha256，小写，可用 certutil -hashfile x.exe SHA256 生成>",
        "notes": "更新说明（可选）"
    }

启用前把 MANIFEST_URL 改成你的 Gitee 地址（仓库需公开，或使用带 token 的 raw 链接）。
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

from PySide6.QtCore import QObject, Signal

APP_VERSION = "1.6"

# 升级 manifest 地址（Gitee 仓库 raw 文件，发布新版时更新仓库里的 latest.json）
MANIFEST_URL = "https://gitee.com/dongyubingsky/dongyubingsky/raw/master/latest.json"

CHUNK = 64 * 1024
_UA = {"User-Agent": "wyj-programmer"}


def _quoted_url(url: str) -> str:
    """对 URL path 中的非 ASCII 字符（如中文文件名）做百分号编码，其余保持不变。"""
    sp = urllib.parse.urlsplit(url)
    path = urllib.parse.quote(sp.path, safe="/%")
    return urllib.parse.urlunsplit((sp.scheme, sp.netloc, path, sp.query, sp.fragment))


class _QuotingRedirectHandler(urllib.request.HTTPRedirectHandler):
    """跟随重定向时对 Location 再次百分号编码（Gitee 附件重定向会带中文文件名）。"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return super().redirect_request(req, fp, code, msg, headers, _quoted_url(newurl))


_OPENER = urllib.request.build_opener(_QuotingRedirectHandler)


def _fetch(url: str, timeout: float = 15.0) -> bytes:
    req = urllib.request.Request(_quoted_url(url), headers=_UA)
    with _OPENER.open(req, timeout=timeout) as r:
        return r.read()


def fetch_latest() -> dict:
    """拉取并解析远端 manifest，返回 {version, url, sha256, notes}。"""
    data = json.loads(_fetch(MANIFEST_URL).decode("utf-8"))
    version = str(data.get("version", "")).strip()
    url = str(data.get("url", "")).strip()
    sha256 = str(data.get("sha256", "")).strip().lower()
    if not version or not url:
        raise ValueError("manifest 缺少 version/url 字段")
    return {"version": version, "url": url, "sha256": sha256,
            "notes": str(data.get("notes", ""))}


def version_tuple(v: str):
    try:
        return tuple(int(x) for x in v.strip().split("."))
    except ValueError:
        return None


def is_new_version(remote: str, local: str = APP_VERSION) -> bool:
    r, l = version_tuple(remote), version_tuple(local)
    if r is None or l is None:
        return remote.strip() != local.strip()
    return r > l


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def build_update_bat(new_exe: Path, target_exe: Path, pid: int) -> str:
    """生成替换脚本：等当前进程退出 → 覆盖旧 exe → 重启 → 自删。"""
    return (
        "@echo off\r\n"
        "rem WYJ PROGRAM auto update\r\n"
        ":loop\r\n"
        f'tasklist /FI "PID eq {pid}" | find "{pid}" >nul\r\n'
        "if not errorlevel 1 (timeout /t 1 /nobreak >nul & goto loop)\r\n"
        f'move /y "{new_exe}" "{target_exe}"\r\n'
        f'start "" "{target_exe}"\r\n'
        'del "%~f0"\r\n'
    )


def launch_replace(new_exe: Path, target_exe: Path) -> Path:
    """写入并后台启动 updater.bat，调用方随后退出进程即可。"""
    bat = Path(tempfile.gettempdir()) / "wyj_programmer_update.bat"
    bat.write_text(build_update_bat(new_exe, target_exe, os.getpid()), encoding="gbk")
    detached = 0x00000008 | 0x08000000  # DETACHED_PROCESS | CREATE_NO_WINDOW
    subprocess.Popen(["cmd", "/c", str(bat)], creationflags=detached, close_fds=True)
    return bat


class UpdateCheckWorker(QObject):
    """拉取远端 manifest（后台线程执行）。"""

    check_done = Signal(dict)
    check_failed = Signal(str)

    def run(self) -> None:
        try:
            self.check_done.emit(fetch_latest())
        except Exception as e:
            self.check_failed.emit(f"{type(e).__name__}: {e}")


class UpdateDownloadWorker(QObject):
    """下载新 exe 并做 sha256 校验（后台线程执行）。"""

    progress = Signal(int, int)  # recv_bytes, total_bytes(可能为 0)
    downloaded = Signal(object)  # Path
    failed = Signal(str)

    def __init__(self, url: str, sha256: str) -> None:
        super().__init__()
        self._url = url
        self._sha = sha256

    def run(self) -> None:
        tmp = Path(tempfile.gettempdir()) / f"wyj_update_{os.getpid()}.exe"
        try:
            req = urllib.request.Request(_quoted_url(self._url), headers=_UA)
            recv = 0
            last = -1
            with _OPENER.open(req, timeout=30) as r, open(tmp, "wb") as f:
                total = int(r.headers.get("Content-Length") or 0)
                while True:
                    block = r.read(CHUNK)
                    if not block:
                        break
                    f.write(block)
                    recv += len(block)
                    step = recv // (256 * 1024)
                    if step != last:  # 限频：每 256KB 发一次进度
                        last = step
                        self.progress.emit(recv, total)
            self.progress.emit(recv, recv or total)
            if self._sha and sha256_file(tmp) != self._sha:
                tmp.unlink(missing_ok=True)
                raise ValueError("sha256 校验失败，安装包可能不完整")
            self.downloaded.emit(tmp)
        except Exception as e:
            if tmp.exists():
                tmp.unlink(missing_ok=True)
            self.failed.emit(f"{type(e).__name__}: {e}")
