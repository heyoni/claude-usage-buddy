"""클릭했을 때 뜨는 말풍선."""

from __future__ import annotations

import objc
from AppKit import (
    NSBezierPath,
    NSColor,
    NSFont,
    NSFontAttributeName,
    NSForegroundColorAttributeName,
    NSGraphicsContext,
    NSShadow,
    NSView,
)
from Foundation import NSMakePoint, NSMakeRect, NSMakeSize, NSString

from .usage import Snapshot, fmt_duration, fmt_tokens

PAD_X = 16.0
PAD_TOP = 13.0
PAD_BOTTOM = 17.0
CONTENT_W = 248.0
TAIL_H = 11.0
TAIL_W = 18.0
CHAMFER = 6.0
BAR_SEGMENTS = 22

H_TITLE = 25.0
H_ROW = 19.0
H_BAR = 26.0
H_DIVIDER = 12.0
H_NOTE = 16.0
H_GAP = 6.0


def _rgb(r, g, b, a=1.0):
    return NSColor.colorWithSRGBRed_green_blue_alpha_(r, g, b, a)


LIGHT = {
    "bg": _rgb(1.0, 0.996, 0.988, 0.98),
    "border": _rgb(0.0, 0.0, 0.0, 0.10),
    "text": _rgb(0.16, 0.14, 0.13),
    "dim": _rgb(0.52, 0.48, 0.45),
    "track": _rgb(0.0, 0.0, 0.0, 0.08),
}
DARK = {
    "bg": _rgb(0.16, 0.148, 0.137, 0.98),
    "border": _rgb(1.0, 1.0, 1.0, 0.12),
    "text": _rgb(0.949, 0.925, 0.898),
    "dim": _rgb(0.60, 0.565, 0.529),
    "track": _rgb(1.0, 1.0, 1.0, 0.10),
}

BAR_OK = _rgb(0.42, 0.647, 0.494)
BAR_WARN = _rgb(0.851, 0.467, 0.341)
BAR_DANGER = _rgb(0.773, 0.271, 0.231)


def _chamfered(rect, c: float):
    """모서리를 둥글리는 대신 45도로 잘라낸 사각형. 도트 그림과 결이 맞는다."""
    x, y = rect.origin.x, rect.origin.y
    w, h = rect.size.width, rect.size.height
    points = [
        (x + c, y), (x + w - c, y), (x + w, y + c), (x + w, y + h - c),
        (x + w - c, y + h), (x + c, y + h), (x, y + h - c), (x, y + c),
    ]
    path = NSBezierPath.bezierPath()
    path.moveToPoint_(NSMakePoint(*points[0]))
    for point in points[1:]:
        path.lineToPoint_(NSMakePoint(*point))
    path.closePath()
    return path


def _stepped_tail(tip_x: float):
    """계단식 꼬리. 매끈한 삼각형 대신 폭이 줄어드는 칸을 쌓아 만든다."""
    step_h = TAIL_H / 3.0
    top = TAIL_H + 2.0
    path = NSBezierPath.bezierPath()
    for i in range(3):
        w = TAIL_W * (1.0 - i / 3.0)
        path.appendBezierPathWithRect_(
            NSMakeRect(tip_x - w / 2, top - (i + 1) * step_h, w, step_h + 0.5)
        )
    return path


def _attrs(font, color):
    return {NSFontAttributeName: font, NSForegroundColorAttributeName: color}


def bar_color(percent: float):
    if percent >= 95:
        return BAR_DANGER
    if percent >= 60:
        return BAR_WARN
    return BAR_OK


def rows_from_snapshot(snap: Snapshot) -> list[dict]:
    """말풍선에 그릴 줄 목록을 만든다."""
    if not snap.has_data:
        return [
            {"type": "title", "text": "Claude 사용량"},
            {"type": "note", "text": "아직 기록이 없어요."},
            {"type": "note", "text": "Claude Code를 한 번 쓰고 오면 채워집니다."},
        ]

    rows: list[dict] = [{"type": "title", "text": "Claude 사용량"}]

    if snap.block is None:
        rows.append({"type": "row", "left": "5시간 블록", "right": "쉬는 중", "dim": True})
        rows.append({"type": "divider"})
    else:
        rows.append(
            {
                "type": "row",
                "left": "5시간 블록",
                "right": f"{fmt_duration(snap.block_remaining)} 남음",
                "dim": True,
            }
        )
        rows.append({"type": "bar", "percent": snap.percent})
        rows.append(
            {
                "type": "row",
                "left": f"${snap.block_cost:.2f}",
                "right": f"{fmt_tokens(snap.block_tokens)} tok",
                "strong": True,
            }
        )
        rows.append({"type": "divider"})

    rows.append(
        {
            "type": "row",
            "left": "오늘",
            "right": f"${snap.today_cost:.2f} · {fmt_tokens(snap.today_tokens)}",
        }
    )
    rows.append(
        {
            "type": "row",
            "left": "최근 7일",
            "right": f"${snap.week_cost:.2f} · {fmt_tokens(snap.week_tokens)}",
        }
    )

    rows.append({"type": "gap"})
    if snap.by_model:
        total = sum(cost for _, cost in snap.by_model) or 1.0
        share = " · ".join(
            f"{name} {cost / total * 100:.0f}%" for name, cost in snap.by_model[:3]
        )
        rows.append({"type": "note", "text": f"오늘 사용 모델  {share}"})

    rows.append({"type": "note", "text": "금액은 API 정가 환산 추정치예요"})
    return rows


def measure(rows: list[dict]) -> tuple[float, float]:
    height = PAD_TOP + PAD_BOTTOM + TAIL_H
    for row in rows:
        kind = row["type"]
        height += {
            "title": H_TITLE,
            "row": H_ROW,
            "bar": H_BAR,
            "divider": H_DIVIDER,
            "note": H_NOTE,
            "gap": H_GAP,
        }[kind]
    return CONTENT_W + PAD_X * 2, height


class BubbleView(NSView):
    """말풍선 본체. 아래쪽 가운데에 꼬리가 달린다."""

    def initWithFrame_(self, frame):
        self = objc.super(BubbleView, self).initWithFrame_(frame)
        if self is None:
            return None
        self._rows: list[dict] = []
        self._tail_dx = 0.0
        return self

    def setRows_(self, rows):
        self._rows = rows
        self.setNeedsDisplay_(True)

    def setTailOffset_(self, dx):
        """말풍선이 화면 끝에서 밀렸을 때도 꼬리가 마스코트를 가리키게 한다."""
        limit = CONTENT_W / 2 - TAIL_W
        self._tail_dx = max(-limit, min(limit, float(dx)))
        self.setNeedsDisplay_(True)

    def isFlipped(self):
        return False

    @objc.python_method
    def _palette(self):
        appearance = self.effectiveAppearance()
        name = appearance.bestMatchFromAppearancesWithNames_(
            ["NSAppearanceNameAqua", "NSAppearanceNameDarkAqua"]
        )
        return DARK if name == "NSAppearanceNameDarkAqua" else LIGHT

    def drawRect_(self, _rect):
        bounds = self.bounds()
        width = bounds.size.width
        height = bounds.size.height
        pal = self._palette()

        body = NSMakeRect(1.0, TAIL_H + 1.0, width - 2.0, height - TAIL_H - 2.0)
        path = _chamfered(body, CHAMFER)
        path.appendBezierPath_(_stepped_tail(width / 2 + self._tail_dx))

        NSGraphicsContext.currentContext().saveGraphicsState()
        shadow = NSShadow.alloc().init()
        shadow.setShadowColor_(NSColor.colorWithSRGBRed_green_blue_alpha_(0, 0, 0, 0.22))
        shadow.setShadowBlurRadius_(14.0)
        shadow.setShadowOffset_(NSMakeSize(0, -3))
        shadow.set()
        pal["bg"].setFill()
        path.fill()
        NSGraphicsContext.currentContext().restoreGraphicsState()

        pal["border"].setStroke()
        path.setLineWidth_(1.0)
        path.stroke()

        self._draw_rows(width, height, pal)

    @objc.python_method
    def _draw_rows(self, width, height, pal):
        x = PAD_X
        y = height - PAD_TOP
        inner = width - PAD_X * 2

        for row in self._rows:
            kind = row["type"]
            if kind == "title":
                y -= H_TITLE
                self._text(row["text"], x, y + 5, NSFont.boldSystemFontOfSize_(13.0), pal["text"])
            elif kind == "row":
                y -= H_ROW
                font = NSFont.systemFontOfSize_(12.0)
                if row.get("strong"):
                    font = NSFont.boldSystemFontOfSize_(13.0)
                left_color = pal["dim"] if row.get("dim") else pal["text"]
                right_color = pal["dim"] if row.get("dim") else pal["text"]
                if row.get("strong"):
                    left_color = BAR_WARN
                self._text(row["left"], x, y + 3, font, left_color)
                self._text_right(row["right"], x + inner, y + 3, font, right_color)
            elif kind == "bar":
                y -= H_BAR
                self._bar(x, y + 8, inner, row["percent"], pal)
            elif kind == "divider":
                y -= H_DIVIDER
                line = NSBezierPath.bezierPath()
                line.moveToPoint_(NSMakePoint(x, y + H_DIVIDER / 2))
                line.lineToPoint_(NSMakePoint(x + inner, y + H_DIVIDER / 2))
                line.setLineWidth_(1.0)
                pal["border"].setStroke()
                line.stroke()
            elif kind == "gap":
                y -= H_GAP
            elif kind == "note":
                y -= H_NOTE
                self._text(row["text"], x, y + 2, NSFont.systemFontOfSize_(10.5), pal["dim"])

    @objc.python_method
    def _bar(self, x, y, width, percent, pal):
        height = 9.0
        label = f"{percent:.0f}%"
        font = NSFont.boldSystemFontOfSize_(11.0)
        label_w = self._width(label, font) + 6.0
        track_w = width - label_w

        pal["track"].setFill()
        NSBezierPath.bezierPathWithRect_(NSMakeRect(x, y, track_w, height)).fill()

        color = bar_color(percent)
        color.setFill()
        gap = 1.5
        seg_w = (track_w - gap * (BAR_SEGMENTS - 1)) / BAR_SEGMENTS
        lit = int(round(BAR_SEGMENTS * min(percent, 100.0) / 100.0))
        for i in range(lit):
            NSBezierPath.bezierPathWithRect_(
                NSMakeRect(x + i * (seg_w + gap), y, seg_w, height)
            ).fill()

        self._text_right(label, x + width, y - 2, font, color)

    # ---------- 텍스트 헬퍼 ----------

    @objc.python_method
    def _text(self, text, x, y, font, color):
        NSString.stringWithString_(text).drawAtPoint_withAttributes_(
            NSMakePoint(x, y), _attrs(font, color)
        )

    @objc.python_method
    def _width(self, text, font):
        return NSString.stringWithString_(text).sizeWithAttributes_(
            _attrs(font, LIGHT["text"])
        ).width

    @objc.python_method
    def _text_right(self, text, right_x, y, font, color):
        self._text(text, right_x - self._width(text, font), y, font, color)
