# SmartPendriveButler.spec
# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_data_files, collect_submodules
import os

# collect package data files (config, data) for guessit and babelfish
datas = collect_data_files('guessit') + collect_data_files('babelfish')

# collect all submodules for guessit and babelfish so dynamic imports are included
hiddenimports = collect_submodules('guessit') + collect_submodules('babelfish')

# optionally add any other explicit hidden imports you found earlier
hiddenimports += [
    'babelfish.converters.alpha2',
    'babelfish.converters'
]

# If you have additional data (icons, assets), include them:
# Example: include your asset folder (if present)
if os.path.isdir('asset'):
    # add tuples: (source, dest_in_exe)
    datas += [ (os.path.join('asset', fname), os.path.join('asset', fname)) for fname in os.listdir('asset') ]

block_cipher = None

a = Analysis(
    ['smart_pendrive_butler.py'],
    pathex=['.'],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
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
    name='SmartPendriveButler',
    debug=False,
    strip=False,
    upx=True,
    console=False,            # set True if you want a console
    icon='asset\\AutoDrive.ico' if os.path.exists('asset\\AutoDrive.ico') else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='SmartPendriveButler'
)
