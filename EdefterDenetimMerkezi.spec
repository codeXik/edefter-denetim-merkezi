# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

project_root = Path.cwd()
frontend_dist = project_root / "frontend" / "dist"
app_icon = project_root / "assets" / "branding" / "e_defter_denetim_merkezi_logo_set" / "edefter-denetim-merkezi.ico"

datas = []
if frontend_dist.exists():
    for file_path in frontend_dist.rglob("*"):
        if file_path.is_file():
            relative_parent = file_path.relative_to(frontend_dist).parent
            target_dir = Path("frontend_dist") / relative_parent
            datas.append((str(file_path), str(target_dir)))

a = Analysis(
    ["src\\edefter_denetim\\desktop_main.py"],
    pathex=[str(project_root / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "bottle",
        "proxy_tools",
        "webview.platforms.edgechromium",
        "webview.platforms.winforms",
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
    name="e-Defter Denetim Merkezi",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=str(app_icon) if app_icon.exists() else None,
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
    upx_exclude=[],
    name="e-Defter Denetim Merkezi",
)
