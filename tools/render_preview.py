"""마스코트와 말풍선을 PNG로 뽑아 본다.

한 장에 표정을 여러 개 늘어놓지만 실제로 떠 있는 마스코트는 한 마리다.
이 스크립트는 그림을 손볼 때 결과를 눈으로 확인하려고 쓴다.

    python tools/render_preview.py out.png
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from AppKit import (  # noqa: E402
    NSApplication,
    NSBitmapImageRep,
    NSCalibratedRGBColorSpace,
    NSColor,
    NSGraphicsContext,
    NSMakeRect,
)
from Foundation import NSMakePoint  # noqa: E402

from buddy import sprite  # noqa: E402
from buddy.bubble import BubbleView, measure, rows_from_snapshot  # noqa: E402
from buddy.usage import Snapshot, UsageIndex, summarize  # noqa: E402

CELL = 170
MOODS = [
    ("happy", False),
    ("busy", True),
    ("worried", False),
    ("panic", False),
    ("sleepy", False),
]


def _rep(width: int, height: int) -> NSBitmapImageRep:
    return NSBitmapImageRep.alloc().initWithBitmapDataPlanes_pixelsWide_pixelsHigh_bitsPerSample_samplesPerPixel_hasAlpha_isPlanar_colorSpaceName_bytesPerRow_bitsPerPixel_(
        None, width, height, 8, 4, True, False, NSCalibratedRGBColorSpace, 0, 0
    )


def main() -> None:
    NSApplication.sharedApplication()
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "preview.png")

    index = UsageIndex()
    index.refresh()
    snap: Snapshot = summarize(index.entries)
    rows = rows_from_snapshot(snap)
    bubble_w, bubble_h = measure(rows)

    width = int(max(CELL * len(MOODS), bubble_w + 40))
    height = int(CELL + bubble_h + 40)

    rep = _rep(width, height)
    ctx = NSGraphicsContext.graphicsContextWithBitmapImageRep_(rep)
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.setCurrentContext_(ctx)

    NSColor.colorWithSRGBRed_green_blue_alpha_(0.96, 0.95, 0.94, 1.0).setFill()
    NSColor.colorWithSRGBRed_green_blue_alpha_(0.96, 0.95, 0.94, 1.0).set()
    from AppKit import NSBezierPath

    NSBezierPath.bezierPathWithRect_(NSMakeRect(0, 0, width, height)).fill()

    # 표정 목록을 아래쪽 한 줄에 늘어놓는다
    for i, (mood, walking) in enumerate(MOODS):
        st = sprite.MascotState()
        st.mood = mood
        st.walking = walking
        st.facing = 1 if i % 2 == 0 else -1
        sprite.step(st, time.time() + i * 0.4)
        NSGraphicsContext.saveGraphicsState()
        tf_rect = NSMakeRect(i * CELL, 0, CELL, CELL)
        NSBezierPath.bezierPathWithRect_(tf_rect).addClip()
        from AppKit import NSAffineTransform

        tf = NSAffineTransform.transform()
        tf.translateXBy_yBy_(i * CELL, 0)
        tf.concat()
        sprite.draw(CELL, CELL, st)
        NSGraphicsContext.restoreGraphicsState()

    NSGraphicsContext.restoreGraphicsState()

    # 말풍선은 뷰의 그리기 코드를 그대로 호출한다.
    # 캐시 비트맵으로 합치면 뷰의 불투명 배경까지 같이 딸려온다.
    view = BubbleView.alloc().initWithFrame_(NSMakeRect(0, 0, bubble_w, bubble_h))
    view.setRows_(rows)

    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.setCurrentContext_(ctx)
    from AppKit import NSAffineTransform as _TF

    tf = _TF.transform()
    tf.translateXBy_yBy_(20, CELL + 20)
    tf.concat()
    view.drawRect_(view.bounds())
    NSGraphicsContext.restoreGraphicsState()

    from AppKit import NSPNGFileType

    data = rep.representationUsingType_properties_(NSPNGFileType, {})
    data.writeToFile_atomically_(str(out), True)
    print(f"wrote {out} ({width}x{height})")


if __name__ == "__main__":
    main()
