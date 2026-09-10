"""사용량 구간별로 마스코트가 어떻게 보이는지 한 장에 그린다.

    python tools/render_states.py docs/states.png
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from AppKit import (  # noqa: E402
    NSAffineTransform,
    NSApplication,
    NSBezierPath,
    NSBitmapImageRep,
    NSCalibratedRGBColorSpace,
    NSColor,
    NSFont,
    NSFontAttributeName,
    NSForegroundColorAttributeName,
    NSGraphicsContext,
    NSMakeRect,
    NSPNGFileType,
)
from Foundation import NSMakePoint, NSString  # noqa: E402

from buddy import sprite  # noqa: E402
from buddy.bubble import BubbleView, measure  # noqa: E402

# (표정, 제목, 설명)
STATES = [
    ("happy", "0 – 49%", "느긋하게 돌아다님"),
    ("busy", "50 – 79%", "걸음이 빨라짐"),
    ("worried", "80 – 94%", "땀을 흘림"),
    ("panic", "95 – 99%", "빨간 땀 + 떨림"),
    ("exhausted", "100% –", "퍼져서 숨만 쉼"),
    ("sleepy", "쉬는 중", "눈 감고 잠"),
]
PERCENTS = {"happy": 24.0, "busy": 63.0, "worried": 87.0, "panic": 97.0, "exhausted": 100.0}

CELL = 210
GAP = 14
LABEL_H = 62


def _rep(width: int, height: int) -> NSBitmapImageRep:
    return NSBitmapImageRep.alloc().initWithBitmapDataPlanes_pixelsWide_pixelsHigh_bitsPerSample_samplesPerPixel_hasAlpha_isPlanar_colorSpaceName_bytesPerRow_bitsPerPixel_(
        None, width, height, 8, 4, True, False, NSCalibratedRGBColorSpace, 0, 0
    )


def _bubble_rows(mood: str) -> list[dict]:
    if mood == "sleepy":
        return [
            {"type": "title", "text": "Claude 사용량"},
            {"type": "note", "text": "지금은 쉬는 중"},
        ]
    return [
        {"type": "title", "text": "Claude 사용량"},
        {"type": "bar", "percent": PERCENTS[mood]},
        {"type": "note", "text": "2시간 41분 뒤 초기화"},
    ]


def _text(text, x, y, size, color, bold=False):
    font = NSFont.boldSystemFontOfSize_(size) if bold else NSFont.systemFontOfSize_(size)
    NSString.stringWithString_(text).drawAtPoint_withAttributes_(
        NSMakePoint(x, y),
        {NSFontAttributeName: font, NSForegroundColorAttributeName: color},
    )


def main() -> None:
    NSApplication.sharedApplication()
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "docs/states.png")

    bubble_h = max(measure(_bubble_rows(mood))[1] for mood, _, _ in STATES)
    col = CELL + GAP
    width = col * len(STATES) - GAP + 40
    height = int(bubble_h) + CELL + LABEL_H + 30

    rep = _rep(int(width), int(height))
    ctx = NSGraphicsContext.graphicsContextWithBitmapImageRep_(rep)
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.setCurrentContext_(ctx)

    NSColor.colorWithSRGBRed_green_blue_alpha_(0.96, 0.95, 0.94, 1.0).setFill()
    NSBezierPath.bezierPathWithRect_(NSMakeRect(0, 0, width, height)).fill()

    ink = NSColor.colorWithSRGBRed_green_blue_alpha_(0.17, 0.16, 0.15, 1.0)
    dim = NSColor.colorWithSRGBRed_green_blue_alpha_(0.17, 0.16, 0.15, 0.55)

    for i, (mood, title, caption) in enumerate(STATES):
        x = 20 + i * col

        _text(title, x + 8, height - 34, 19.0, ink, bold=True)
        _text(caption, x + 8, height - 56, 13.0, dim)

        rows = _bubble_rows(mood)
        bw, bh = measure(rows)
        view = BubbleView.alloc().initWithFrame_(NSMakeRect(0, 0, bw, bh))
        view.setRows_(rows)
        view.setTailOffset_(0)
        NSGraphicsContext.saveGraphicsState()
        tf = NSAffineTransform.transform()
        tf.translateXBy_yBy_(x + (CELL - bw) / 2, CELL + 10)
        tf.concat()
        view.drawRect_(view.bounds())
        NSGraphicsContext.restoreGraphicsState()

        st = sprite.MascotState()
        st.mood = mood
        st.walking = mood == "busy"
        sprite.step(st, time.time() + i * 0.7)
        NSGraphicsContext.saveGraphicsState()
        tf = NSAffineTransform.transform()
        tf.translateXBy_yBy_(x, 0)
        tf.concat()
        sprite.draw(CELL, CELL, st)
        NSGraphicsContext.restoreGraphicsState()

    NSGraphicsContext.restoreGraphicsState()
    rep.representationUsingType_properties_(NSPNGFileType, {}).writeToFile_atomically_(
        str(out), True
    )
    print(f"wrote {out} ({int(width)}x{int(height)})")


if __name__ == "__main__":
    main()
