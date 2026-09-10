"""클릭했을 때 뜨는 말풍선.

마스코트와 같은 도트 감성으로 그린다. 모서리는 둥글리지 않고 칸을 덜어내고,
테두리와 꼬리도 칸을 쌓아 만든다. 그림자도 흐리지 않고 한 칸 밀어 찍는다.
한글은 도트 폰트로 찍을 수 없어서 글자만 시스템 폰트를 쓴다.
"""

from __future__ import annotations

import objc
from AppKit import (
    NSBezierPath,
    NSColor,
    NSFont,
    NSFontAttributeName,
    NSForegroundColorAttributeName,
    NSFontWeightMedium,
    NSGraphicsContext,
    NSView,
)
from Foundation import NSMakePoint, NSMakeRect, NSString

from .usage import Snapshot, fmt_duration, fmt_tokens

P = 3.0                 # 도트 한 칸
BORDER = 3.0            # 테두리 두께 (한 칸)
CORNER = 2 * P          # 모서리에서 덜어내는 크기
PAD_X = 12.0
PAD_TOP = 10.0
PAD_BOTTOM = 12.0
CONTENT_W = 196.0
TAIL_W = 6 * P
TAIL_H = 3 * P

H_TITLE = 24.0
H_ROW = 20.0
H_BAR = 24.0
H_NOTE = 17.0
H_GAP = 6.0

_HEIGHTS = {"title": H_TITLE, "row": H_ROW, "bar": H_BAR, "note": H_NOTE, "gap": H_GAP}


def _rgb(r, g, b, a=1.0):
    return NSColor.colorWithSRGBRed_green_blue_alpha_(r, g, b, a)


# 마스코트와 같은 배색
INK = _rgb(0.169, 0.161, 0.153)          # 몸통 색 = 말풍선 바탕
CREAM = _rgb(0.965, 0.937, 0.886)        # 눈·테두리 색 = 글자
CREAM_DIM = _rgb(0.965, 0.937, 0.886, 0.55)
TRACK = _rgb(0.965, 0.937, 0.886, 0.16)
DROP = _rgb(0.0, 0.0, 0.0, 0.28)

BAR_OK = _rgb(0.451, 0.729, 0.541)
BAR_WARN = _rgb(0.878, 0.514, 0.349)
BAR_DANGER = _rgb(0.851, 0.310, 0.267)


def bar_color(percent: float):
    if percent >= 95:
        return BAR_DANGER
    if percent >= 60:
        return BAR_WARN
    return BAR_OK


def rows_from_snapshot(snap: Snapshot) -> list[dict]:
    """말풍선에 그릴 줄 목록. 지금 블록만 보여주고 나머지는 CLI 에 맡긴다."""
    if not snap.has_data:
        return [
            {"type": "title", "text": "Claude 사용량"},
            {"type": "note", "text": "아직 기록이 없어요"},
        ]

    rows: list[dict] = [{"type": "title", "text": "Claude 사용량"}]

    if snap.block is None:
        rows.append({"type": "row", "left": "5시간 블록", "right": "쉬는 중", "dim": True})
        return rows

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
    return rows


def measure(rows: list[dict]) -> tuple[float, float]:
    height = PAD_TOP + PAD_BOTTOM + BORDER * 2 + TAIL_H
    for row in rows:
        height += _HEIGHTS[row["type"]]
    return CONTENT_W + PAD_X * 2 + BORDER * 2, height


def _notched_rect(x, y, w, h, c):
    """네 모서리에서 정사각형을 하나씩 덜어낸 사각형. 도트 그림의 둥근 모서리."""
    points = [
        (x + c, y), (x + w - c, y), (x + w - c, y + c), (x + w, y + c),
        (x + w, y + h - c), (x + w - c, y + h - c), (x + w - c, y + h), (x + c, y + h),
        (x + c, y + h - c), (x, y + h - c), (x, y + c), (x + c, y + c),
    ]
    path = NSBezierPath.bezierPath()
    path.moveToPoint_(NSMakePoint(*points[0]))
    for point in points[1:]:
        path.lineToPoint_(NSMakePoint(*point))
    path.closePath()
    return path


def _silhouette(width: float, height: float, tip_x: float, inset: float):
    """말풍선 바깥선(inset=0)과 안쪽 면(inset=BORDER)을 같은 규칙으로 만든다."""
    body_bottom = TAIL_H
    body = _notched_rect(
        inset,
        body_bottom + inset,
        width - inset * 2,
        height - body_bottom - inset * 2,
        CORNER - inset,
    )

    if inset == 0:
        # 아래로 갈수록 좁아지는 칸 세 개
        steps = [(6 * P, P), (4 * P, P), (2 * P, P)]
        y = body_bottom
        for w, h in steps:
            y -= h
            body.appendBezierPathWithRect_(NSMakeRect(tip_x - w / 2, y, w, h))
    else:
        # 바깥선보다 한 칸씩 좁고 한 칸 짧게. 몸통과 만나는 지점은 겹쳐서 이어 붙인다.
        body.appendBezierPathWithRect_(
            NSMakeRect(tip_x - 2 * P, body_bottom - P, 4 * P, P + BORDER)
        )
        body.appendBezierPathWithRect_(
            NSMakeRect(tip_x - P, body_bottom - 2 * P, 2 * P, P)
        )
    return body


class BubbleView(NSView):
    """말풍선 본체. 아래쪽에 계단식 꼬리가 달린다."""

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

    def drawRect_(self, _rect):
        bounds = self.bounds()
        width, height = bounds.size.width, bounds.size.height
        tip_x = width / 2 + self._tail_dx

        ctx = NSGraphicsContext.currentContext()
        ctx.saveGraphicsState()
        ctx.setShouldAntialias_(False)

        # 흐린 그림자 대신 한 칸 밀어 찍은 단단한 그림자
        shadow = _silhouette(width - P, height - P, tip_x, 0)
        transform = NSBezierPath.bezierPath()
        transform.appendBezierPath_(shadow)
        DROP.setFill()
        self._offset(transform, P, -P).fill()

        CREAM.setFill()
        _silhouette(width - P, height - P, tip_x, 0).fill()
        INK.setFill()
        _silhouette(width - P, height - P, tip_x, BORDER).fill()

        ctx.restoreGraphicsState()
        self._draw_rows(width, height)

    @objc.python_method
    def _offset(self, path, dx, dy):
        from AppKit import NSAffineTransform

        tf = NSAffineTransform.transform()
        tf.translateXBy_yBy_(dx, dy)
        return tf.transformBezierPath_(path)

    @objc.python_method
    def _draw_rows(self, width, height):
        x = BORDER + PAD_X
        y = height - P - BORDER - PAD_TOP
        inner = width - P - (BORDER + PAD_X) * 2

        for row in self._rows:
            kind = row["type"]
            y -= _HEIGHTS[kind]
            if kind == "title":
                self._text(row["text"], x, y + 5, NSFont.boldSystemFontOfSize_(13.0), CREAM)
            elif kind == "row":
                strong = row.get("strong", False)
                font = _num_font(13.5) if strong else NSFont.systemFontOfSize_(12.0)
                left = BAR_WARN if strong else (CREAM_DIM if row.get("dim") else CREAM)
                right = CREAM if strong else (CREAM_DIM if row.get("dim") else CREAM)
                self._text(row["left"], x, y + 3, font, left)
                self._text_right(row["right"], x + inner, y + 3, font, right)
            elif kind == "bar":
                self._bar(x, y + 8, inner, row["percent"])
            elif kind == "note":
                self._text(row["text"], x, y + 3, NSFont.systemFontOfSize_(11.5), CREAM_DIM)

    @objc.python_method
    def _bar(self, x, y, width, percent):
        ctx = NSGraphicsContext.currentContext()
        ctx.saveGraphicsState()
        ctx.setShouldAntialias_(False)

        height = 3 * P
        font = _num_font(11.5)
        label = f"{percent:.0f}%"
        label_w = self._width(label, font) + 8.0
        track_w = width - label_w

        seg = 2 * P
        gap = P
        count = max(1, int((track_w + gap) // (seg + gap)))
        used = count * (seg + gap) - gap

        TRACK.setFill()
        for i in range(count):
            NSBezierPath.bezierPathWithRect_(
                NSMakeRect(x + i * (seg + gap), y, seg, height)
            ).fill()

        bar_color(percent).setFill()
        lit = int(round(count * min(percent, 100.0) / 100.0))
        for i in range(lit):
            NSBezierPath.bezierPathWithRect_(
                NSMakeRect(x + i * (seg + gap), y, seg, height)
            ).fill()

        ctx.restoreGraphicsState()
        self._text_right(label, x + used + label_w, y - 2, font, bar_color(percent))

    @objc.python_method
    def _text(self, text, x, y, font, color):
        NSString.stringWithString_(text).drawAtPoint_withAttributes_(
            NSMakePoint(x, y), _attrs(font, color)
        )

    @objc.python_method
    def _width(self, text, font):
        return NSString.stringWithString_(text).sizeWithAttributes_(
            _attrs(font, CREAM)
        ).width

    @objc.python_method
    def _text_right(self, text, right_x, y, font, color):
        self._text(text, right_x - self._width(text, font), y, font, color)


def _attrs(font, color):
    return {NSFontAttributeName: font, NSForegroundColorAttributeName: color}


def _num_font(size: float):
    """숫자 폭이 일정한 폰트. 값이 바뀌어도 자리가 흔들리지 않는다."""
    return NSFont.monospacedDigitSystemFontOfSize_weight_(size, NSFontWeightMedium)
