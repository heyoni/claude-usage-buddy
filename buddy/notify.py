"""macOS 알림 센터로 알림을 보낸다.

NSUserNotification 은 .app 번들을 요구하고 이미 폐기된 API라,
어디서든 동작하는 osascript 를 쓴다.
"""

from __future__ import annotations

import subprocess


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def send(title: str, message: str, subtitle: str = "") -> None:
    script = f'display notification "{_escape(message)}" with title "{_escape(title)}"'
    if subtitle:
        script += f' subtitle "{_escape(subtitle)}"'
    try:
        subprocess.run(
            ["osascript", "-e", script],
            check=False,
            timeout=5,
            capture_output=True,
        )
    except (OSError, subprocess.SubprocessError):
        pass


class Notifier:
    """같은 알림을 반복해서 띄우지 않도록 상태를 들고 있는다."""

    def __init__(self, cfg: dict) -> None:
        self.cfg = cfg
        self._fired: set[int] = set()
        self._block_start: float | None = None

    def update(self, snapshot) -> None:
        notify_cfg = self.cfg.get("notify", {})
        if not notify_cfg.get("enabled", True):
            return

        block = snapshot.block
        start = block.start if block else None

        if start != self._block_start:
            previous_fired = bool(self._fired)
            self._fired.clear()
            if (
                notify_cfg.get("on_block_reset", True)
                and self._block_start is not None
                and previous_fired
                and start is not None
            ):
                send("Claude 사용량", "새 5시간 블록이 시작됐어요.", "이전 블록 기록이 초기화됐습니다")
            self._block_start = start

        if block is None:
            return

        from .usage import fmt_duration, fmt_tokens

        for threshold in sorted(notify_cfg.get("thresholds", [])):
            if snapshot.percent >= threshold and threshold not in self._fired:
                self._fired.add(threshold)
                send(
                    "Claude 사용량",
                    f"${snapshot.block_cost:.2f} · {fmt_tokens(snapshot.block_tokens)} tok",
                    f"5시간 블록 {threshold}% 도달 · {fmt_duration(snapshot.block_remaining)} 남음",
                )
