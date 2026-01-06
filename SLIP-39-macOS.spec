# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files
from PyInstaller.utils.hooks import collect_all

datas = []
binaries = []
hiddenimports = ['slip39', 'tzdata']
datas += collect_data_files('shamir_mnemonic')
datas += collect_data_files('slip39')
tmp_ret = collect_all('tzdata')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('zoneinfo')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['SLIP-39.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
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
    name='SLIP-39',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity='EAA134BE299C43D27E33E2B8645FF4CF55DE8A92',
    entitlements_file='SLIP-39.metadata/entitlements.plist',
    icon=['images/SLIP-39.icns'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='SLIP-39',
)
app = BUNDLE(
    coll,
    name='SLIP-39.app',
    icon='images/SLIP-39.icns',
    version='14.0.2',
    info_plist={
        'NSPrincipalClass': 'NSApplication',
        'NSAppleScriptEnabled': False,
        'LSBackgroundOnly': False,
        'NSRequiresAquaSystemAppearance': 'No',
        'CFBundleSupportedPlatforms': ['MacOSX'],
        'CFBundleIdentifier': 'ca.kundert.perry.SLIP39',
        'CFBundleVersion': '14.0.2',
        'CFBundlePackageType':'APPL',
        'LSApplicationCategoryType':'public.app-category.utilities',
        'LSMinimumSystemVersion':'10.15',
        'NSHumanReadableCopyright':"Copyright © 2023 Perry Kundert.",
        'ITSAppUsesNonExemptEncryption': False,
    },
    bundle_identifier='ca.kundert.perry.SLIP39',
)
