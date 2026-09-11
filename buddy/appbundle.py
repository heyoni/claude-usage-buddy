"""더블클릭으로 실행할 수 있는 .app 번들을 만든다.

~/Applications/Claude Usage Buddy.app 에 두면 런치패드와 Spotlight 에서 찾을 수
있다. 안에 든 건 가상환경의 명령을 실행하는 셸 스크립트 하나와 아이콘뿐이라,
저장소를 옮기거나 지워도 가상환경만 남아 있으면 동작한다.
"""

from __future__ import annotations

import plistlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

APP_NAME = "Claude Usage Buddy"
BUNDLE_ID = "com.github.claude-usage-buddy"
APP_DIR = Path.home() / "Applications"
APP_PATH = APP_DIR / f"{APP_NAME}.app"

# iconutil 이 요구하는 파일 이름과 크기
_ICON_SIZES = [
    ("icon_16x16.png", 16), ("icon_16x16@2x.png", 32),
    ("icon_32x32.png", 32), ("icon_32x32@2x.png", 64),
    ("icon_128x128.png", 128), ("icon_128x128@2x.png", 256),
    ("icon_256x256.png", 256), ("icon_256x256@2x.png", 512),
    ("icon_512x512.png", 512), ("icon_512x512@2x.png", 1024),
]


def _render_icon(size: int, out: Path) -> None:
    """크림색 둥근 바탕 위에 도트 마스코트를 그린 아이콘 한 장."""
    from AppKit import (
        NSBezierPath,
        NSBitmapImageRep,
        NSCalibratedRGBColorSpace,
        NSColor,
        NSGraphicsContext,
        NSMakeRect,
        NSPNGFileType,
    )

    from . import sprite

    rep = NSBitmapImageRep.alloc().initWithBitmapDataPlanes_pixelsWide_pixelsHigh_bitsPerSample_samplesPerPixel_hasAlpha_isPlanar_colorSpaceName_bytesPerRow_bitsPerPixel_(
        None, size, size, 8, 4, True, False, NSCalibratedRGBColorSpace, 0, 0
    )
    ctx = NSGraphicsContext.graphicsContextWithBitmapImageRep_(rep)
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.setCurrentContext_(ctx)

    # macOS 아이콘 관례대로 가장자리를 조금 비우고 둥근 사각형을 깐다
    inset = size * 0.05
    radius = size * 0.22
    NSColor.colorWithSRGBRed_green_blue_alpha_(0.965, 0.937, 0.886, 1.0).setFill()
    NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
        NSMakeRect(inset, inset, size - inset * 2, size - inset * 2), radius, radius
    ).fill()

    # 창에서는 땀방울 자리로 여백을 두지만 아이콘에선 필요 없다.
    # 다만 둥근 바탕(폭 90%) 안에 팔까지 들어가야 하므로 그보다 조금 작게.
    st = sprite.MascotState()
    cell = max(1, int(size * 0.78 / sprite.GRID_W))
    sprite.draw(size, size, st, cell=cell)

    NSGraphicsContext.restoreGraphicsState()
    rep.representationUsingType_properties_(NSPNGFileType, {}).writeToFile_atomically_(str(out), True)


def _build_icns(out: Path) -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        iconset = Path(tmp) / "icon.iconset"
        iconset.mkdir()
        for name, size in _ICON_SIZES:
            _render_icon(size, iconset / name)
        result = subprocess.run(
            ["iconutil", "-c", "icns", str(iconset), "-o", str(out)],
            capture_output=True,
        )
        return result.returncode == 0


def install() -> Path:
    exe = Path(sys.executable).with_name("claude-usage-buddy")
    if not exe.exists():
        raise SystemExit("먼저 설치해 주세요: ./install.sh")

    contents = APP_PATH / "Contents"
    macos = contents / "MacOS"
    resources = contents / "Resources"
    if APP_PATH.exists():
        shutil.rmtree(APP_PATH)
    macos.mkdir(parents=True)
    resources.mkdir(parents=True)

    launcher = macos / "launcher"
    launcher.write_text(f'#!/bin/bash\nexec "{exe}"\n')
    launcher.chmod(0o755)

    has_icon = _build_icns(resources / "icon.icns")

    info = {
        "CFBundleName": APP_NAME,
        "CFBundleDisplayName": APP_NAME,
        "CFBundleIdentifier": BUNDLE_ID,
        "CFBundleVersion": "0.1.0",
        "CFBundleShortVersionString": "0.1.0",
        "CFBundlePackageType": "APPL",
        "CFBundleExecutable": "launcher",
        "LSUIElement": True,          # Dock 에 아이콘을 남기지 않는다 (마스코트가 곧 UI)
        "LSMinimumSystemVersion": "12.0",
        "NSHighResolutionCapable": True,
    }
    if has_icon:
        info["CFBundleIconFile"] = "icon"
    with (contents / "Info.plist").open("wb") as fh:
        plistlib.dump(info, fh)

    # Finder 가 새 아이콘을 바로 반영하도록
    subprocess.run(["touch", str(APP_PATH)], check=False)
    return APP_PATH


def uninstall() -> None:
    if APP_PATH.exists():
        shutil.rmtree(APP_PATH)
