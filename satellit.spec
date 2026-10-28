# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller-Spec für Satellit (Windows-One-Folder-Build).

Bauen:
    pip install pyinstaller
    pyinstaller satellit.spec

Ergebnis: dist\\Satellit\\Satellit.exe samt static\\ und – falls vorhanden –
ffmpeg\\ffmpeg.exe. ffmpeg bitte vorab nach ./ffmpeg/ffmpeg.exe legen, dann
wird es mit eingepackt (sonst muss ffmpeg im PATH liegen).

Ein Tray-Build ohne Konsolenfenster entsteht mit console=False.
"""

import os
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

datas = [("static", "static")]
if os.path.exists(os.path.join("ffmpeg", "ffmpeg.exe")):
    datas.append(("ffmpeg/ffmpeg.exe", "ffmpeg"))

hiddenimports = []
for mod in ("sounddevice", "websocket", "opuslib", "pystray", "PIL", "requests"):
    try:
        hiddenimports += collect_submodules(mod)
    except Exception:
        pass

a = Analysis(
    ["winmain.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "pytest"],
    cipher=block_cipher,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="Satellit",
    debug=False,
    strip=False,
    upx=True,
    console=False,          # True = Konsolenfenster zum Mitlesen
    icon=None,
)
coll = COLLECT(
    exe, a.binaries, a.zipfiles, a.datas,
    strip=False, upx=True, name="Satellit",
)
