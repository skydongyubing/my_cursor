#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WYJ PROGRAM 一键发布脚本：改版本号 → 打包 → 发布到 Gitee → 验证升级链路。

用法（建议用 .venv 里的 python 运行）:
  .venv\\Scripts\\python.exe release.py 1.5
  .venv\\Scripts\\python.exe release.py 1.5 --notes "修复xx问题"
  .venv\\Scripts\\python.exe release.py 1.5 --skip-build      # 复用已有 exe
  .venv\\Scripts\\python.exe release.py 1.5 --dry-run         # 只演练，不动 Gitee

Gitee 私人令牌来源（按优先级）: --token > 环境变量 GITEE_TOKEN > 运行时隐藏输入。
令牌仅本次运行使用，不会写入任何文件。
"""
import argparse
import base64
import getpass
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OWNER, REPO = "dongyubingsky", "dongyubingsky"
API = f"https://gitee.com/api/v5/repos/{OWNER}/{REPO}"
RAW_MANIFEST = f"https://gitee.com/{OWNER}/{REPO}/raw/master/latest.json"
UPDATER = ROOT / "src" / "updater.py"
SPEC = ROOT / "src" / "main.spec"
# 产物/附件使用固定文件名，升级时原地覆盖；版本区分靠 APP_VERSION（标题栏显示）
EXE_NAME = "威宇佳烧录.exe"
UA = {"User-Agent": "wyj-release"}
CHUNK = 1 << 20


# ---------- Gitee HTTP ----------
def _quoted_url(url: str) -> str:
    sp = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit(
        (sp.scheme, sp.netloc, urllib.parse.quote(sp.path, safe="/%"), sp.query, sp.fragment))


class _QuotingRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return super().redirect_request(req, fp, code, msg, headers, _quoted_url(newurl))


_OPENER = urllib.request.build_opener(_QuotingRedirect)


def _api(method: str, path: str, token: str, body: dict | None = None, timeout: float = 120):
    """调用 Gitee API。GET 走 query token，其余放进 JSON body。"""
    url = f"{API}{path}"
    if method == "GET":
        url += ("&" if "?" in url else "?") + f"access_token={token}"
    data = None
    headers = dict(UA)
    if body is not None:
        payload = dict(body)
        if method != "GET":
            payload["access_token"] = token
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode() or "{}")


def _download(url: str, timeout: float = 600) -> bytes:
    req = urllib.request.Request(_quoted_url(url), headers=UA)
    with _OPENER.open(req, timeout=timeout) as r:
        return r.read()


# ---------- 步骤 ----------
def bump_version(ver: str) -> None:
    """修改 updater.py 的 APP_VERSION（exe 文件名固定，不随版本变化）。"""
    text = UPDATER.read_text(encoding="utf-8")
    text, n1 = re.subn(r'APP_VERSION = "[\d.]+"', f'APP_VERSION = "{ver}"', text)
    if n1 != 1:
        raise SystemExit(f"版本号定位失败：updater.py 命中 {n1} 处")
    UPDATER.write_text(text, encoding="utf-8")
    print(f"[1/6] 版本号已更新 -> {ver}（src/updater.py）")


def build() -> None:
    print("[2/6] PyInstaller 打包中，约 1~2 分钟……")
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
           "--workpath", str(ROOT / "src" / "build"),
           "--distpath", str(ROOT / "src" / "dist"), str(SPEC)]
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        print(r.stdout[-2000:]); print(r.stderr[-2000:])
        raise SystemExit("打包失败")


def exe_sha256(ver: str) -> str:
    exe = ROOT / "src" / "dist" / EXE_NAME
    if not exe.exists():
        raise SystemExit(f"找不到 {exe}，请先打包或去掉 --skip-build")
    h = hashlib.sha256()
    with open(exe, "rb") as f:
        for blk in iter(lambda: f.read(CHUNK), b""):
            h.update(blk)
    print(f"[3/6] exe 就绪，sha256 = {h.hexdigest()[:24]}…")
    return h.hexdigest()


def publish(ver: str, sha: str, notes: str, token: str) -> None:
    tag = f"v{ver}"
    # 确保 Release 存在
    releases = _api("GET", "/releases", token)
    rel = next((r for r in releases if r.get("tag_name") == tag), None)
    if rel is None:
        rel = _api("POST", "/releases", token, {
            "tag_name": tag, "name": tag, "body": notes,
            "target_commitish": "master", "prerelease": False})
        print(f"[4/6] 已创建 Release {tag} (id={rel['id']})")
    else:
        print(f"[4/6] Release {tag} 已存在 (id={rel['id']})，复用")
    rel_id = rel["id"]

    fname = EXE_NAME
    # 删除同名旧附件
    for att in _api("GET", f"/releases/{rel_id}/attach_files", token):
        if att.get("name") == fname:
            _api("DELETE", f"/releases/{rel_id}/attach_files/{att['id']}", token)
            print(f"      已删除旧附件 {att['id']}")
    # 上传新附件
    exe = ROOT / "src" / "dist" / fname
    boundary = "----wyjrelease9f3a1c"
    with open(exe, "rb") as f:
        exe_bytes = f.read()
    head = (f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{fname}"\r\n'
            "Content-Type: application/octet-stream\r\n\r\n").encode("utf-8")
    tail = f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        f"{API}/releases/{rel_id}/attach_files?access_token={token}",
        data=head + exe_bytes + tail, method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}", **UA})
    with urllib.request.urlopen(req, timeout=600) as r:
        r.read()
    print(f"[4/6] 附件已上传（{len(exe_bytes)} 字节）")

    # 更新 latest.json
    latest = {"version": ver, "notes": notes,
              "url": f"https://gitee.com/{OWNER}/{REPO}/releases/download/{tag}/{fname}",
              "sha256": sha}
    content = base64.b64encode(
        json.dumps(latest, ensure_ascii=False, indent=2).encode("utf-8")).decode()
    try:
        meta = _api("GET", "/contents/latest.json", token)
        _api("PUT", "/contents/latest.json", token,
             {"content": content, "sha": meta["sha"], "branch": "master",
              "message": f"release {tag}"})
    except urllib.error.HTTPError as e:
        if e.code == 404:
            _api("POST", "/contents/latest.json", token,
                 {"content": content, "branch": "master", "message": f"release {tag}"})
        else:
            raise
    print("[5/6] latest.json 已更新")


def verify(ver: str, sha: str) -> None:
    req = urllib.request.Request(RAW_MANIFEST, headers={**UA, "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = json.loads(r.read().decode())
    assert raw["version"] == ver and raw["sha256"] == sha, f"manifest 不一致: {raw}"
    got = hashlib.sha256(_download(raw["url"])).hexdigest()
    assert got == sha, "下载内容 sha256 不一致！"
    print(f"[6/6] 验证通过：manifest 与线上附件 sha256 一致，v{ver} 已可被自动升级")


def main() -> None:
    ap = argparse.ArgumentParser(description="WYJ PROGRAM 一键发布")
    ap.add_argument("version", help="新版本号，如 1.5")
    ap.add_argument("--notes", default="", help="更新说明（进入 latest.json 与 Release 描述）")
    ap.add_argument("--token", help="Gitee 私人令牌（默认取 GITEE_TOKEN 或运行时输入）")
    ap.add_argument("--skip-build", action="store_true", help="跳过打包，复用已有 exe")
    ap.add_argument("--dry-run", action="store_true", help="只改版本号并打印计划，不调用 Gitee")
    args = ap.parse_args()
    if not re.fullmatch(r"\d+(\.\d+)+", args.version):
        raise SystemExit("版本号格式应为 x.y 或 x.y.z，如 1.5")

    bump_version(args.version)
    if not args.skip_build:
        build()
    else:
        print("[2/6] 跳过打包（--skip-build）")
    sha = exe_sha256(args.version)
    if args.dry_run:
        print("[dry-run] 停止。以上改动可 git checkout 还原，或直接去掉 --dry-run 正式发布。")
        return

    token = args.token or os.environ.get("GITEE_TOKEN") or getpass.getpass("Gitee 私人令牌: ").strip()
    if not token:
        raise SystemExit("未提供令牌")
    notes = args.notes or f"威宇佳烧录 {args.version}"
    publish(args.version, sha, notes, token)
    verify(args.version, sha)
    print("\n完成！记得：① git 提交版本号改动 ② 到 Gitee 作废本次使用的令牌")


if __name__ == "__main__":
    main()
