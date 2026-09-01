# -*- mode: python ; coding: utf-8 -*-

import os
from pathlib import Path


steam_api_path = os.environ.get('SAVESHIFT_STEAM_API_PATH')
steam_binaries = []

if steam_api_path:
    resolved_steam_api_path = Path(steam_api_path)

    if not resolved_steam_api_path.is_file():
        raise FileNotFoundError(
            f'steam_api64.dll was not found: {resolved_steam_api_path}'
        )

    steam_binaries.append((str(resolved_steam_api_path), '.'))


a = Analysis(
    ['run_saveshift.py'],
    pathex=[],
    binaries=steam_binaries,
    datas=[
        ('assets/icons/SaveShift.ico', 'assets/icons'),
        (
            'app/resources/cloudflare/index.js',
            'app/resources/cloudflare',
        ),
    ],
    hiddenimports=[
        'app.package_transport.encrypted_transport',
        'app.steam.native_ugc_client',
        'app.steam.ugc_transport',
    ],
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
    [],
    exclude_binaries=True,
    name='SaveShift',
    icon='assets/icons/SaveShift.ico',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='SaveShift',
)
