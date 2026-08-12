# -*- mode: python ; coding: utf-8 -*-
import os
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None
PROJECT_ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

hiddenimports = [
    "selenium",
    "selenium.webdriver",
    "selenium.webdriver.chrome",
    "selenium.webdriver.chrome.service",
    "selenium.webdriver.chrome.options",
    "urllib3",
    "requests",
    "websockets",
    "PIL",
    "win32clipboard",
    "pywinauto",
]
hiddenimports += collect_submodules("selenium")
hiddenimports += collect_submodules("pywinauto")
hiddenimports += collect_submodules("selenium.webdriver.common.selenium_manager")
hiddenimports += collect_submodules("selenium.webdriver.chrome.service")

bootstrap = '''
import os
os.environ.setdefault("DJANGO_BASE_URL", "https://agents.zettalgor.com")
os.environ.setdefault("AGENT_WS_URL", "wss://agents.zettalgor.com/ws/agent/")
'''
bootstrap_path = os.path.join(SPECPATH, "_env_agent.py")
with open(bootstrap_path, "w", encoding="utf-8") as f:
    f.write(bootstrap)


a = Analysis(
    [bootstrap_path, os.path.join(SPECPATH, "app.py")],
    pathex=[PROJECT_ROOT],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "numpy", "pandas", "scipy"],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    name="agent",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
