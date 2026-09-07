# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for 威宇佳烧录.

Build from repo root (paths resolve relative to this spec file):

    pyinstaller --noconfirm --clean --workpath src\\build --distpath src\\dist src\\main.spec
"""
import os

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

a = Analysis(
    ["main.py"],
    pathex=[ROOT],
    binaries=[],
    datas=[(os.path.join(ROOT, "icon_chip.ico"), ".")],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="威宇佳烧录",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(ROOT, "icon_chip.ico"),
)
