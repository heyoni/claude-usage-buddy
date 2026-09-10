"""말풍선이 뜨고 사라지는 흐름을 실제 컨트롤러로 확인한다.

창을 만들되 런루프는 돌리지 않고 tick 을 직접 호출한다.

    ~/.claude-usage-buddy/venv/bin/python tests/test_bubble_flow.py
"""

import sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from AppKit import NSApplication, NSApplicationActivationPolicyAccessory
app = NSApplication.sharedApplication()
app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)

from buddy.app import BuddyController
c = BuddyController.alloc().init()

c._mouse_is_down = lambda: True   # 버튼을 누르고 있는 상황을 흉내낸다

def tick(n=1):
    for _ in range(n):
        c.tick_(None)

def report(label):
    print(f"{label:28s} visible={c.bubble_window.isVisible()!s:5s} "
          f"alpha={c.bubble_window.alphaValue():.2f} "
          f"pinned={c.bubble_pinned!s:5s} until={c.bubble_until:.0f} "
          f"fade={c._fade_started is not None}")

print("=== 짧게 클릭 (설정된 시간 뒤 사라져야 함) ===")
c.press_began(); tick(2); c.press_ended()
report("클릭 직후")
t0 = time.time()
while time.time() - t0 < 6.0:
    tick(); time.sleep(1/30)
    if not c.bubble_window.isVisible():
        print(f"  -> {time.time()-t0:.1f}초 만에 사라짐")
        break
report("6초 경과")

print()
print("=== 꾹 누르기 (고정되어야 함) ===")
c.press_began()
t0 = time.time()
while time.time() - t0 < 1.2:
    tick(); time.sleep(1/30)
c.press_ended()
report("꾹 누른 뒤")
t0 = time.time()
while time.time() - t0 < 6.5:
    tick(); time.sleep(1/30)
report("6.5초 더 기다림")

print()
print("=== 고정 상태에서 클릭하면 닫혀야 함 ===")
c.press_began(); tick(2); c.press_ended()
t0 = time.time()
while time.time() - t0 < 1.0:
    tick(); time.sleep(1/30)
    if not c.bubble_window.isVisible():
        print(f"  -> {time.time()-t0:.2f}초 만에 사라짐 (페이드)")
        break
report("클릭 후")
