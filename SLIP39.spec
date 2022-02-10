# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files

datas = []
datas += collect_data_files('shamir_mnemonic')


block_cipher = None


a = Analysis(['SLIP39.py'],
             pathex=[],
             binaries=[],
             datas=datas,
             hiddenimports=[],
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
          [],
          exclude_binaries=True,
          name='SLIP39',
          debug=False,
          bootloader_ignore_signals=False,
          strip=False,
          upx=True,
          console=False,
          disable_windowed_traceback=False,
          target_arch=None,
          codesign_identity='Developer ID Application: Perry Kundert (ZD8TVTCXDS)',
          entitlements_file='SLIP39.metadata/entitlements.plist' )
coll = COLLECT(exe,
               a.binaries,
               a.zipfiles,
               a.datas, 
               strip=False,
               upx=True,
               upx_exclude=[],
               name='SLIP39')
app = BUNDLE(coll,
             name='SLIP39.app',
             icon='images/SLIP39.icns',
             version='6.5.4',
             info_plist={
                 'CFBundleVersion':'6.5.4',
                 'LSApplicationCategoryType':'public.app-category.finance',
                 'LSMinimumSystemVersion':'10.15.0',
             },
             bundle_identifier='ca.kundert.perry.SLIP39')

