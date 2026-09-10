"""클릭했을 때 뜨는 말풍선.

만화에 나오는 둥근 말풍선을 도트로 찍는다. 모서리는 원을 칸으로 근사해
계단처럼 깎이고, 꼬리는 왼쪽 아래로 비스듬히 내려간다. 테두리는 도안을
한 칸 깎아낸 안쪽 면을 덧칠해 만든다 — 마스코트를 그리는 방식과 같다.
한글은 도트 폰트로 찍을 수 없어서 글자만 시스템 폰트를 쓴다.
"""

from __future__ import annotations

from collections import defaultdict

import objc
from AppKit import (
    NSBezierPath,
    NSColor,
    NSFont,
    NSFontAttributeName,
    NSFontWeightMedium,
    NSForegroundColorAttributeName,
    NSGraphicsContext,
    NSView,
)
from Foundation import NSMakePoint, NSMakeRect, NSString

from .usage import Snapshot, fmt_duration

U = 4.0                 # 도트 한 칸
RADIUS_CELLS = 8        # 모서리 원의 반지름 (칸)
PAD_X = 24.0
PAD_TOP = 16.0
PAD_BOTTOM = 18.0
CONTENT_W = 168.0

# 꼬리 도안. (칸x, 칸y) — y 0 이 맨 아래 끝, 위로 갈수록 넓어지며 오른쪽으로 눕는다
_TAIL = [
    (0, 0), (1, 0),                              # 끝
    (0, 1), (1, 1), (2, 1),
    (1, 2), (2, 2), (3, 2),
    (1, 3), (2, 3), (3, 3), (4, 3),
    (2, 4), (3, 4), (4, 4), (5, 4),              # 풍선에 붙는 줄
]
TAIL_ROWS = 5
TAIL_H = TAIL_ROWS * U
_TAIL_TIP_COL = 0       # 꼬리 끝이 놓이는 칸 (마스코트를 가리키는 지점)

H_TITLE = 24.0
H_ROW = 20.0
H_BAR = 24.0
H_NOTE = 18.0
_HEIGHTS = {"title": H_TITLE, "row": H_ROW, "bar": H_BAR, "note": H_NOTE}


def _rgb(r, g, b, a=1.0):
    return NSColor.colorWithSRGBRed_green_blue_alpha_(r, g, b, a)


# 마스코트와 같은 배색을 뒤집어 쓴다 — 크림색 종이에 숯색 선
PAPER = _rgb(0.965, 0.937, 0.886)
INK = _rgb(0.169, 0.161, 0.153)
INK_DIM = _rgb(0.169, 0.161, 0.153, 0.52)
TRACK = _rgb(0.169, 0.161, 0.153, 0.14)
DROP = _rgb(0.0, 0.0, 0.0, 0.22)

BAR_OK = _rgb(0.306, 0.549, 0.388)
BAR_WARN = _rgb(0.769, 0.337, 0.184)
BAR_DANGER = _rgb(0.690, 0.169, 0.133)


def bar_color(percent: float):
    if percent >= 95:
        return BAR_DANGER
    if percent >= 60:
        return BAR_WARN
    return BAR_OK


def rows_from_snapshot(snap: Snapshot) -> list[dict]:
    """말풍선에 그릴 줄 목록.

    지금 얼마나 썼고 언제 초기화되는지만 남긴다. 금액·토큰 수와
    하루·주 단위 합계는 CLI(`python -m buddy --cli`)에서 본다.
    """
    if not snap.has_data:
        return [
            {"type": "title", "text": "Claude 사용량"},
            {"type": "note", "text": "아직 기록이 없어요"},
        ]

    if snap.block is None:
        return [
            {"type": "title", "text": "Claude 사용량"},
            {"type": "note", "text": "지금은 쉬는 중"},
        ]

    return [
        {"type": "title", "text": "Claude 사용량"},
        {"type": "bar", "percent": snap.percent},
        {"type": "note", "text": f"{fmt_duration(snap.block_remaining)} 뒤 초기화"},
    ]


def _round_up(value: float) -> float:
    """칸 격자에 맞춰 올림. 반 칸짜리 조각이 생기면 도트가 흐려진다."""
    return -(-value // U) * U


def measure(rows: list[dict]) -> tuple[float, float]:
    body = PAD_TOP + PAD_BOTTOM + sum(_HEIGHTS[row["type"]] for row in rows)
    return _round_up(CONTENT_W + PAD_X * 2), _round_up(body) + TAIL_H


def _balloon_cells(wc: int, hc: int, radius: int) -> set[tuple[int, int]]:
    """모서리가 원으로 깎인 사각형을 칸 단위로 채운다."""
    cells = set()
    for y in range(hc):
        for x in range(wc):
            qx = max(radius - (x + 0.5), (x + 0.5) - (wc - radius), 0.0)
            qy = max(radius - (y + 0.5), (y + 0.5) - (hc - radius), 0.0)
            if qx * qx + qy * qy <= radius * radius:
                cells.add((x, y))
    return cells


def _erode(cells: set[tuple[int, int]]) -> set[tuple[int, int]]:
    """상하좌우가 모두 채워진 칸만 남긴다. 남은 가장자리가 테두리가 된다."""
    return {
        (x, y)
        for (x, y) in cells
        if (x + 1, y) in cells
        and (x - 1, y) in cells
        and (x, y + 1) in cells
        and (x, y - 1) in cells
    }


def _runs(cells: set[tuple[int, int]]):
    """같은 줄에서 이어진 칸을 한 덩어리로 묶는다. 사각형 수를 줄여 준다."""
    rows: dict[int, list[int]] = defaultdict(list)
    for (x, y) in cells:
        rows[y].append(x)
    for y, xs in rows.items():
        xs.sort()
        start = prev = xs[0]
        for x in xs[1:]:
            if x == prev + 1:
                prev = x
                continue
            yield start, prev, y
            start = prev = x
        yield start, prev, y


def _shape(wc: int, hc: int, tail_col: int) -> tuple[set, set]:
    """말풍선 전체 칸과, 한 칸 깎아낸 안쪽 칸."""
    cells = _balloon_cells(wc, hc, RADIUS_CELLS)
    for (dx, dy) in _TAIL:
        cells.add((tail_col - _TAIL_TIP_COL + dx, dy - TAIL_ROWS))
    return cells, _erode(cells)


class BubbleView(NSView):
    """말풍선 본체. 도안을 만들어 두고 크기가 바뀔 때만 다시 계산한다."""

    def initWithFrame_(self, frame):
        self = objc.super(BubbleView, self).initWithFrame_(frame)
        if self is None:
            return None
        self._rows: list[dict] = []
        self._tail_col = None   # 아직 정해지지 않음 — 기본은 가운데
        self._cache_key = None
        self._cache = None
        return self

    def setRows_(self, rows):
        self._rows = rows
        self.setNeedsDisplay_(True)

    def setTailOffset_(self, dx):
        """말풍선이 화면 끝에서 밀렸을 때도 꼬리 끝이 마스코트를 가리키게 한다."""
        wc = max(1, int(self.bounds().size.width / U))
        col = int(round((self.bounds().size.width / 2 + float(dx)) / U)) - 1
        col = max(RADIUS_CELLS, min(wc - RADIUS_CELLS - 6, col))
        if col != self._tail_col:
            self._tail_col = col
            self.setNeedsDisplay_(True)

    def isFlipped(self):
        return False

    @objc.python_method
    def _shape_for(self, width, height):
        wc = int(width / U)
        hc = int((height - TAIL_H) / U)
        tail_col = self._tail_col if self._tail_col is not None else wc // 2 - 2
        key = (wc, hc, tail_col)
        if key != self._cache_key:
            self._cache_key = key
            self._cache = _shape(wc, hc, tail_col)
        return self._cache

    def drawRect_(self, _rect):
        bounds = self.bounds()
        width, height = bounds.size.width, bounds.size.height
        cells, inner = self._shape_for(width, height)

        ctx = NSGraphicsContext.currentContext()
        ctx.saveGraphicsState()
        ctx.setShouldAntialias_(False)

        # 흐린 그림자 대신 한 칸 밀어 찍은 단단한 그림자
        DROP.setFill()
        self._fill(cells, U, -U)
        INK.setFill()
        self._fill(cells, 0, 0)
        PAPER.setFill()
        self._fill(inner, 0, 0)

        ctx.restoreGraphicsState()
        self._draw_rows(width, height)

    @objc.python_method
    def _fill(self, cells, dx, dy):
        path = NSBezierPath.bezierPath()
        for x0, x1, y in _runs(cells):
            path.appendBezierPathWithRect_(
                NSMakeRect(x0 * U + dx, TAIL_H + y * U + dy, (x1 - x0 + 1) * U, U)
            )
        path.fill()

    @objc.python_method
    def _draw_rows(self, width, height):
        x = PAD_X
        y = height - PAD_TOP
        inner = width - PAD_X * 2

        for row in self._rows:
            kind = row["type"]
            y -= _HEIGHTS[kind]
            if kind == "title":
                self._text(row["text"], x, y + 5, NSFont.boldSystemFontOfSize_(13.0), INK)
            elif kind == "row":
                strong = row.get("strong", False)
                font = _num_font(13.5) if strong else NSFont.systemFontOfSize_(12.0)
                left = BAR_WARN if strong else (INK_DIM if row.get("dim") else INK)
                right = INK if strong else (INK_DIM if row.get("dim") else INK)
                self._text(row["left"], x, y + 3, font, left)
                self._text_right(row["right"], x + inner, y + 3, font, right)
            elif kind == "bar":
                self._bar(x, y + 8, inner, row["percent"])
            elif kind == "note":
                self._text(row["text"], x, y + 3, NSFont.systemFontOfSize_(11.5), INK_DIM)

    @objc.python_method
    def _bar(self, x, y, width, percent):
        ctx = NSGraphicsContext.currentContext()
        ctx.saveGraphicsState()
        ctx.setShouldAntialias_(False)

        height = 2 * U
        font = _num_font(11.5)
        label = f"{percent:.0f}%"
        label_w = self._width(label, font) + 8.0
        track_w = width - label_w

        seg, gap = 2 * U, U
        count = max(1, int((track_w + gap) // (seg + gap)))
        used = count * (seg + gap) - gap

        for color, upto in ((TRACK, count), (bar_color(percent), int(round(count * min(percent, 100.0) / 100.0)))):
            color.setFill()
            for i in range(upto):
                NSBezierPath.bezierPathWithRect_(
                    NSMakeRect(x + i * (seg + gap), y, seg, height)
                ).fill()

        ctx.restoreGraphicsState()
        self._text_right(label, x + used + label_w, y - 3, font, bar_color(percent))

    @objc.python_method
    def _text(self, text, x, y, font, color):
        NSString.stringWithString_(text).drawAtPoint_withAttributes_(
            NSMakePoint(x, y), _attrs(font, color)
        )

    @objc.python_method
    def _width(self, text, font):
        return NSString.stringWithString_(text).sizeWithAttributes_(_attrs(font, INK)).width

    @objc.python_method
    def _text_right(self, text, right_x, y, font, color):
        self._text(text, right_x - self._width(text, font), y, font, color)


def _attrs(font, color):
    return {NSFontAttributeName: font, NSForegroundColorAttributeName: color}


def _num_font(size: float):
    """숫자 폭이 일정한 폰트. 값이 바뀌어도 자리가 흔들리지 않는다."""
    return NSFont.monospacedDigitSystemFontOfSize_weight_(size, NSFontWeightMedium)
