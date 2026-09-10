"""마스코트 도안이 상태·방향에 따라 어떻게 나오는지 눈으로 확인한다.

걸을 때 윗몸만 기울기 때문에, 눈처럼 여러 줄에 걸친 부분은 함께 움직이지
않으면 어긋난다. 도안을 고칠 때 이 출력으로 확인한다.

    ~/.claude-usage-buddy/venv/bin/python tests/test_sprite_frames.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from buddy import sprite  # noqa: E402

CASES = [
    ("평온 · 서 있음", "happy", False, 1, 0.0),
    ("평온 · 눈 깜빡임 · 걷기", "happy", True, 1, 1.0),
    ("바쁨 · 오른쪽 걷기", "busy", True, 1, 0.0),
    ("바쁨 · 왼쪽 걷기", "busy", True, -1, 0.0),
    ("땀 · 걷기", "worried", True, 1, 0.0),
    ("당황 · 서 있음", "panic", False, 1, 0.0),
    ("당황 · 오른쪽 걷기", "panic", True, 1, 0.0),
    ("당황 · 왼쪽 걷기", "panic", True, -1, 0.0),
    ("잠", "sleepy", False, 1, 0.0),
]


def eye_columns(rows: list[str]) -> list[set[int]]:
    """눈('o')이 있는 칸 번호를 줄마다 모은다."""
    return [{i for i, ch in enumerate(row) if ch == "o"} for row in rows]


def main() -> int:
    failures = 0
    for label, mood, walking, facing, blink in CASES:
        st = sprite.MascotState()
        st.mood, st.walking, st.facing, st.blink = mood, walking, facing, blink
        rows = sprite.frame_rows(st)

        print(f"--- {label} ---")
        for row in rows:
            print("   " + row.replace("#", "█").replace("o", "·"))

        # 눈이 여러 줄에 걸쳐 있다면 줄마다 같은 칸에 있어야 한다
        eyes = [cols for cols in eye_columns(rows) if cols]
        if len(eyes) > 1 and any(cols != eyes[0] for cols in eyes[1:]):
            print(f"   !! 눈이 줄마다 어긋납니다: {eyes}")
            failures += 1

    print()
    print("모든 도안 정상" if not failures else f"{failures}개 도안에 문제")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
