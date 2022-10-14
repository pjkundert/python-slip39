# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files

datas = []
datas += collect_data_files('shamir_mnemonic')
datas += collect_data_files('slip39')


block_cipher = None


a = Analysis(['SLIP-39.py'],
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
          name='SLIP-39',
          debug=False,
          bootloader_ignore_signals=False,
          strip=False,
          upx=True,
          console=False,
          disable_windowed_traceback=False,
          target_arch=None,
          codesign_identity='Developer ID Application: Perry Kundert (ZD8TVTCXDS)',
          entitlements_file='./SLIP-39.metadata/entitlements.plist' )
coll = COLLECT(exe,
               a.binaries,
               a.zipfiles,
               a.datas, 
               strip=False,
               upx=True,
               upx_exclude=[],
               name='SLIP-39')
app = BUNDLE(coll,
             name='SLIP-39.app',
             icon='images/SLIP-39.icns',
             version='9.1.0',
             info_plist={
                 'CFBundleVersion':'9.1.0',
                 'CFBundlePackageType':'APPL',
                 'LSApplicationCategoryType':'public.app-category.finance',
                 'LSMinimumSystemVersion':'10.15.0',
             },
             bundle_identifier='ca.kundert.perry.SLIP39')
