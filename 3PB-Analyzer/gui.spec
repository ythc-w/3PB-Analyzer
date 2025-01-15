# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_data_files

added_files = collect_data_files('tkinter')

a = Analysis(
    ['gui.py', 'analysis.py', 'config.py', 'utils.py'],
    pathex=['.'],
    binaries=[],
    datas=[('3PB.log', '.')],  # 删除图标
    hiddenimports=[],
    hookspath=['.'],
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
    [], # 将 a.binaries 删除
    [], # 将 a.datas 删除
    name='gui',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
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
    upx=True,
    name='gui'
)