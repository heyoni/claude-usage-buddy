"""마스코트를 도트(픽셀) 그림으로 그린다.

격자 한 칸을 정사각형 하나로 찍는다. 칸 크기를 정수로 맞추고
안티에일리어싱을 꺼서, 확대해도 도트가 뭉개지지 않는다.
"""

from __future__ import annotations

from AppKit import NSBezierPath, NSColor, NSGraphicsContext
from Foundation import NSMakeRect

# 몸통은 진한 숯색, 눈과 테두리는 크림색
BODY = NSColor.colorWithSRGBRed_green_blue_alpha_(0.169, 0.161, 0.153, 1.0)
EYE = NSColor.colorWithSRGBRed_green_blue_alpha_(0.965, 0.937, 0.886, 1.0)
OUTLINE = NSColor.colorWithSRGBRed_green_blue_alpha_(0.965, 0.937, 0.886, 0.92)
SHADOW = NSColor.colorWithSRGBRed_green_blue_alpha_(0.0, 0.0, 0.0, 0.13)
SWEAT = NSColor.colorWithSRGBRed_green_blue_alpha_(0.408, 0.706, 0.925, 1.0)
ALERT = NSColor.colorWithSRGBRed_green_blue_alpha_(0.851, 0.341, 0.298, 1.0)
SPARK = NSColor.colorWithSRGBRed_green_blue_alpha_(1.0, 1.0, 1.0, 1.0)

GRID_W = 14
GRID_H = 9
MARGIN_CELLS = 4   # 도안 양옆·위아래로 남겨 두는 여백 (땀방울, z 자리)

# 도트 도안. '#' 몸통, 'o' 눈, ' ' 빈칸
#   위 두 줄은 머리, 가운데 튀어나온 두 줄은 팔, 아래 두 줄은 다리
_BASE = [
    "  ##########  ",
    "  #o######o#  ",
    "  #o######o#  ",
    "##############",
    "##############",
    "  ##########  ",
    "  ##########  ",
]
_LEGS_STAND = ["   # #  # #   ", "   # #  # #   "]

# 다 써 버렸을 때. 다리에 힘이 풀려 주저앉고 몸이 옆으로 퍼진다.
# 머리·눈·팔 위치는 서 있을 때와 같게 두어야 같은 녀석으로 보인다.
# 높이도 9줄로 맞춰야 바닥이 어긋나지 않는다.
_LYING = [
    "              ",
    "              ",
    "              ",
    "  ##########  ",
    "  #oo####oo#  ",
    "##############",
    " ############ ",
    " ############ ",
    "  #  #  #  #  ",
]

# 걸을 때 번갈아 딛는 다리
_LEGS_A = ["   # #  # #   ", "   #    #     "]
_LEGS_B = ["   # #  # #   ", "     #    #   "]


def _rows(chars: str) -> list[str]:
    return list(chars)


def _set(row: str, col: int, ch: str) -> str:
    if 0 <= col < len(row):
        return row[:col] + ch + row[col + 1 :]
    return row


class MascotState:
    """그리기에 필요한 순간 상태."""

    def __init__(self) -> None:
        self.mood = "happy"
        self.walking = False
        self.facing = 1          # 1 오른쪽, -1 왼쪽
        self.blink = 0.0         # 1 이면 눈 감음
        self.bob = 0             # 0 또는 1 (칸 단위로만 튄다)
        self.step_phase = 0      # 걷는 다리 프레임
        self.zzz = 0.0           # 0~1 반복
        self.jitter = 0          # 당황했을 때 좌우로 떨림
        self.dragging = False
        # 이전 구현과 호환을 위해 남겨둔 값들
        self.lean = 0.0
        self.squash = 0.0


def hit_extent(size: float) -> tuple[float, float]:
    """마우스 판정용 반너비/반높이. 도트 몸이 가로로 길어서 원이 아니라 사각형이다."""
    cell = cell_size(size)
    return cell * GRID_W / 2 + cell * 1.5, cell * GRID_H / 2 + cell * 1.5


def top_offset(size: float) -> float:
    """창 중심에서 머리 꼭대기까지의 거리.

    도안 높이의 절반에 크림색 테두리 한 칸과 위아래로 튀는 폭 한 칸을 더한다.
    말풍선 꼬리를 이보다 위에 두어야 머리와 겹치지 않는다.
    """
    cell = cell_size(size)
    return cell * GRID_H / 2 + cell * 2


def bottom_offset(size: float) -> float:
    """창 중심에서 발밑 그림자 아래까지의 거리."""
    cell = cell_size(size)
    return cell * GRID_H / 2 + cell * 2


def cell_size(size: float) -> int:
    """창 크기에 맞는 도트 한 칸 크기(정수)."""
    return max(2, int(size / (GRID_W + MARGIN_CELLS * 2)))


def frame_rows(st: MascotState) -> list[str]:
    """현재 상태에 맞는 도안 한 장을 만든다."""
    if st.mood == "exhausted":
        return list(_LYING)

    rows = list(_BASE)

    if st.walking:
        rows += _LEGS_A if st.step_phase == 0 else _LEGS_B
    else:
        rows += _LEGS_STAND

    # 눈 모양 — 위쪽 한 칸을 몸통으로 덮으면 반쯤 감은 눈이 된다
    closed = st.blink >= 0.5 or st.mood == "sleepy"
    if closed:
        rows[1] = _set(_set(rows[1], 3, "#"), 10, "#")
        if st.mood == "sleepy":
            # 자는 눈은 가로로 한 칸 더 길게 그어서 감은 티가 나게 한다
            rows[2] = _set(_set(rows[2], 4, "o"), 9, "o")

    # 걸을 때는 윗몸을 진행 방향으로 한 칸 기울인다
    if st.walking:
        shift = 1 if st.facing > 0 else -1
        for i in (0, 1, 2):
            rows[i] = _shift(rows[i], shift)

    return rows


def _shift(row: str, delta: int) -> str:
    if delta > 0:
        return " " * delta + row[:-delta]
    if delta < 0:
        return row[-delta:] + " " * (-delta)
    return row


def draw(width: float, height: float, st: MascotState) -> None:
    """현재 그래픽 컨텍스트에 마스코트 한 프레임을 찍는다."""
    ctx = NSGraphicsContext.currentContext()
    ctx.saveGraphicsState()
    ctx.setShouldAntialias_(False)

    cell = cell_size(min(width, height))
    rows = frame_rows(st)
    grid_h = len(rows)

    # 정수 좌표에 딱 맞춰야 도트가 흐려지지 않는다
    origin_x = int((width - GRID_W * cell) / 2) + st.jitter * (cell // 2)
    origin_y = int(height * 0.5 - (grid_h * cell) / 2) + st.bob * cell

    _draw_shadow(width, origin_y, cell, st)

    def rect(col: int, row: int) -> NSMakeRect:
        # 도안은 위에서 아래로 읽지만 화면 좌표는 아래에서 위로 올라간다
        return NSMakeRect(
            origin_x + col * cell,
            origin_y + (grid_h - 1 - row) * cell,
            cell,
            cell,
        )

    filled = {
        (c, r)
        for r, line in enumerate(rows)
        for c, ch in enumerate(line)
        if ch in "#o"
    }

    OUTLINE.setFill()
    for (col, row) in _outline_cells(filled):
        NSBezierPath.bezierPathWithRect_(rect(col, row)).fill()

    BODY.setFill()
    for r, line in enumerate(rows):
        for c, ch in enumerate(line):
            if ch == "#":
                NSBezierPath.bezierPathWithRect_(rect(c, r)).fill()

    EYE.setFill()
    for r, line in enumerate(rows):
        for c, ch in enumerate(line):
            if ch == "o":
                NSBezierPath.bezierPathWithRect_(rect(c, r)).fill()

    if st.mood in ("worried", "panic", "exhausted"):
        _draw_sweat(rect, filled, st)
    if st.mood == "sleepy":
        _draw_zzz(origin_x, origin_y, cell, grid_h, st)

    ctx.restoreGraphicsState()


def _outline_cells(filled: set[tuple[int, int]]) -> set[tuple[int, int]]:
    """채워진 칸에 맞닿은 빈 칸 — 어떤 배경에서도 실루엣이 보이게 한다."""
    out: set[tuple[int, int]] = set()
    for (col, row) in filled:
        for dc, dr in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            cell = (col + dc, row + dr)
            if cell not in filled:
                out.add(cell)
    return out


def _draw_shadow(width: float, origin_y: int, cell: int, st: MascotState) -> None:
    shrink = cell if st.bob else 0
    w = cell * 8 - shrink * 2
    SHADOW.setFill()
    NSBezierPath.bezierPathWithRect_(
        NSMakeRect(int((width - w) / 2), origin_y - cell, w, cell)
    ).fill()


# 물방울 도트. 위가 뾰족하고 아래가 둥글다.
_DROP_PATTERN = [
    ".#.",
    "###",
    "###",
    "###",
]


def _draw_sweat(rect, body: set[tuple[int, int]], st: MascotState) -> None:
    """머리 옆으로 흘러내리는 땀방울. 사용량이 많을 때만 나온다.

    한 칸짜리 점은 무슨 표시인지 알기 어려워서, 테두리까지 있는 물방울
    모양으로 몸통과 같은 배색 규칙을 따라 그린다. 팔과 겹치지 않도록
    몸통 바깥 여백에 두고, 테두리도 몸통 위에는 찍지 않는다.
    """
    # 머리 오른쪽 위 모서리에 붙여야 몸에서 난 땀처럼 보인다.
    # 도안 위쪽 여백에 두므로 팔(3~4행)과 겹칠 일이 없다.
    fall = int(st.zzz * 2)
    left = GRID_W - 1 if st.facing > 0 else -2
    # 서 있을 땐 머리 위 여백에, 누워 있을 땐 몸 옆에 붙인다
    top = (4 if st.mood == "exhausted" else -2) + fall

    cells = {
        (left + c, top + r)
        for r, line in enumerate(_DROP_PATTERN)
        for c, ch in enumerate(line)
        if ch == "#"
    }

    OUTLINE.setFill()
    for (col, row) in _outline_cells(cells) - body:
        NSBezierPath.bezierPathWithRect_(rect(col, row)).fill()

    (ALERT if st.mood in ("panic", "exhausted") else SWEAT).setFill()
    for (col, row) in cells:
        NSBezierPath.bezierPathWithRect_(rect(col, row)).fill()

    # 방울 안쪽 반짝임 한 칸
    SPARK.colorWithAlphaComponent_(0.75).setFill()
    NSBezierPath.bezierPathWithRect_(rect(left, top + 2)).fill()


_Z_PATTERN = ["###", "..#", ".#.", "#..", "###"]


def _draw_zzz(origin_x: int, origin_y: int, cell: int, grid_h: int, st: MascotState) -> None:
    """자는 동안 머리 위로 떠오르는 z. 몸통과 같은 배색이라 배경을 안 탄다."""
    unit = max(1, cell // 3)
    for i in range(2):
        phase = (st.zzz + i * 0.5) % 1.0
        alpha = max(0.0, 1.0 - phase)
        if alpha < 0.05:
            continue
        base_x = origin_x + (GRID_W - 4) * cell + int(phase * cell) + i * cell
        base_y = origin_y + grid_h * cell + int(phase * cell) + i * (cell // 2)

        cells = {
            (c, r)
            for r, line in enumerate(_Z_PATTERN)
            for c, ch in enumerate(line)
            if ch == "#"
        }

        def rect(col: int, row: int):
            return NSMakeRect(
                base_x + col * unit,
                base_y + (len(_Z_PATTERN) - 1 - row) * unit,
                unit,
                unit,
            )

        OUTLINE.colorWithAlphaComponent_(alpha * 0.92).setFill()
        for (col, row) in _outline_cells(cells):
            NSBezierPath.bezierPathWithRect_(rect(col, row)).fill()
        BODY.colorWithAlphaComponent_(alpha).setFill()
        for (col, row) in cells:
            NSBezierPath.bezierPathWithRect_(rect(col, row)).fill()


def step(st: MascotState, t: float) -> None:
    """시간 t(초)에 맞춰 애니메이션 값을 갱신한다. 전부 칸 단위로만 움직인다."""
    if st.mood == "exhausted":
        # 가쁜 숨만 쉰다
        st.bob = int(t * 2.4) % 2
        st.step_phase = 0
        st.jitter = 0
        st.zzz = (t * 1.3) % 1.0
        return

    if st.mood == "sleepy":
        st.bob = int(t * 1.2) % 2
        st.step_phase = 0
        st.jitter = 0
        st.zzz = (t * 0.4) % 1.0
        return

    if st.walking:
        st.step_phase = int(t * 7) % 2
        st.bob = st.step_phase
    else:
        st.step_phase = 0
        st.bob = int(t * 1.8) % 2

    if st.dragging:
        st.bob = int(t * 9) % 2
        st.jitter = (int(t * 12) % 2) - 0
    elif st.mood == "panic":
        st.jitter = (int(t * 14) % 2)
    else:
        st.jitter = 0

    if st.mood in ("worried", "panic"):
        st.zzz = (t * 1.1) % 1.0
