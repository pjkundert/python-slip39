# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files

datas = []
datas += collect_data_files('shamir_mnemonic')
datas += collect_data_files('slip39')


block_cipher = None


a = Analysis(['SLIP39.py'],
             pathex=[],
             binaries=[],
             datas=datas,
             hiddenimports=['slip39'],
             hookspath=[],
             hooksconfig={},
             runtime_hooks=[],
             excludes=[],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher,
             noarchive=False)
pyz = PYZ(a.pure, a.zipped_data,
             cipher=block_cipher)

exe = EXE(pyz,
          a.scripts,
          a.binaries,
          a.zipfiles,
          a.datas,  
          [],
          name='SLIP39',
          debug=False,
          bootloader_ignore_signals=False,
          strip=False,
          upx=True,
          upx_exclude=[],
          runtime_tmpdir=None,
          console=False,
          disable_windowed_traceback=False,
          target_arch=None,
          codesign_identity='Developer ID Application: Perry Kundert (ZD8TVTCXDS)',
          entitlements_file='./SLIP39.metadata/entitlements.plist' )
app = BUNDLE(exe,
             name='SLIP39.app',
             icon='images/SLIP39.icns',
             version='7.0.1',
             info_plist={
                 'CFBundleVersion':'7.0.1',
                 'CFBundlePackageType':'APPL',
                 'LSApplicationCategoryType':'public.app-category.finance',
                 'LSMinimumSystemVersion':'10.15.0',
             },
             bundle_identifier='ca.kundert.perry.SLIP39')

