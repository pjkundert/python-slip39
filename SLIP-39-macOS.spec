# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files

datas = []
datas += collect_data_files('shamir_mnemonic')
datas += collect_data_files('slip39')


a = Analysis(
    ['SLIP-39.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=['slip39'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='SLIP-39',
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
    codesign_identity='DDB5489E29389E9081E0A2FD83B6555D1B101829',
    entitlements_file='./SLIP-39.metadata/entitlements.plist',
)
app = BUNDLE(
    exe,
    name='SLIP-39.app',
    icon='images/SLIP-39.icns',
    version='11.1.1',
    info_plist={
        'CFBundleVersion':'11.1.1',
        'CFBundlePackageType':'APPL',
        'LSApplicationCategoryType':'public.app-category.utilities',
        'LSMinimumSystemVersion':'10.15.0',
        'NSHumanReadableCopyright':"Copyright © 2023 Perry Kundert.",
    },
    bundle_identifier='ca.kundert.perry.SLIP39',
)
