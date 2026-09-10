"""마스코트 창, 이동, 말풍선을 묶는 앱 본체."""

from __future__ import annotations

import random
import threading
import time

import objc
from AppKit import (
    NSApp,
    NSApplication,
    NSApplicationActivationPolicyAccessory,
    NSBackingStoreBuffered,
    NSColor,
    NSEvent,
    NSFloatingWindowLevel,
    NSMenu,
    NSMenuItem,
    NSScreen,
    NSStatusWindowLevel,
    NSTimer,
    NSView,
    NSWindow,
    NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowCollectionBehaviorFullScreenAuxiliary,
    NSWindowCollectionBehaviorStationary,
    NSWindowStyleMaskBorderless,
    NSWorkspace,
)
from Foundation import NSMakePoint, NSMakeRect, NSObject

from . import autostart, config, sprite
from .bubble import BubbleView, measure, rows_from_snapshot
from .notify import Notifier
from .usage import UsageIndex, summarize

BASE_SIZE = 132.0        # 마스코트 창 한 변 (배율 1.0 = 메뉴의 "보통", 여백 포함)
WALK_SPEED = 46.0        # 초당 이동 픽셀
FRAME_INTERVAL = 1.0 / 30.0
DRAG_THRESHOLD = 4.0     # 이만큼 넘게 움직이면 클릭이 아니라 끌기로 본다
SCALES = [("아주 작게", 0.6), ("작게", 0.8), ("보통", 1.0), ("크게", 1.4), ("아주 크게", 1.7)]
DEMO_CYCLE = ["happy", "busy", "worried", "panic", "exhausted", "sleepy"]
DEMO_SECONDS = 4.0      # --demo cycle 에서 상태를 바꾸는 간격
LONG_PRESS_SECONDS = 0.8    # 이만큼 누르고 있으면 말풍선을 고정한다
FADE_SECONDS = 0.28         # 사라질 때 투명해지는 시간


def _new_window(width: float, height: float, level: int) -> NSWindow:
    window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
        NSMakeRect(0, 0, width, height),
        NSWindowStyleMaskBorderless,
        NSBackingStoreBuffered,
        False,
    )
    window.setOpaque_(False)
    window.setBackgroundColor_(NSColor.clearColor())
    window.setHasShadow_(False)
    window.setLevel_(level)
    window.setCollectionBehavior_(
        NSWindowCollectionBehaviorCanJoinAllSpaces
        | NSWindowCollectionBehaviorStationary
        | NSWindowCollectionBehaviorFullScreenAuxiliary
    )
    return window


class MascotView(NSView):
    """마스코트를 그리고 마우스를 받는 뷰."""

    def initWithFrame_controller_(self, frame, controller):
        self = objc.super(MascotView, self).initWithFrame_(frame)
        if self is None:
            return None
        self._controller = controller
        self._grab = None
        self._down_at = None
        return self

    def isFlipped(self):
        return False

    def drawRect_(self, _rect):
        bounds = self.bounds()
        sprite.draw(bounds.size.width, bounds.size.height, self._controller.state)

    def mouseDown_(self, event):
        location = NSEvent.mouseLocation()
        self._down_at = (location.x, location.y)
        self._grab = (
            location.x - self._controller.pos_x,
            location.y - self._controller.pos_y,
        )
        self._controller.press_began()

    def mouseDragged_(self, _event):
        if self._grab is None:
            return
        location = NSEvent.mouseLocation()
        if self._down_at and not self._controller.state.dragging:
            moved = abs(location.x - self._down_at[0]) + abs(location.y - self._down_at[1])
            if moved < DRAG_THRESHOLD:
                return
            self._controller.begin_drag()
        self._controller.move_to(location.x - self._grab[0], location.y - self._grab[1])

    def mouseUp_(self, _event):
        was_drag = self._controller.state.dragging
        self._grab = None
        self._down_at = None
        if was_drag:
            self._controller.end_drag()
        else:
            self._controller.press_ended()

    def rightMouseDown_(self, event):
        self._controller.show_menu(event, self)


class BuddyController(NSObject):
    """상태 머신 + 갱신 스레드."""

    def init(self):
        self = objc.super(BuddyController, self).init()
        if self is None:
            return None

        self.cfg = config.load()
        config.ensure_file()
        self.force_mood = None   # --demo 로 지정한 표정. 실제 사용량을 덮어쓴다.
        self.state = sprite.MascotState()
        self.notifier = Notifier(self.cfg)

        self.index = UsageIndex(retention_days=self.cfg["retention_days"])
        self.snapshot = summarize(
            [], self.cfg["block_hours"], self.cfg.get("block_cost_limit")
        )
        self._pending = None
        self._refresh_now = threading.Event()

        scale = float(self.cfg["mascot"].get("scale") or 1.0)
        # 창 크기와 위치를 정수로 맞춰야 도트가 다시 샘플링되지 않는다
        self.size = float(round(BASE_SIZE * max(0.5, min(3.0, scale))))
        self.speed = WALK_SPEED * float(self.cfg["mascot"].get("speed") or 1.0)

        self.pos_x = None
        self.pos_y = None
        self._build_windows()
        self._place_initial()

        self.walk_state = "idle"
        self.state_until = time.time() + 2.0
        self.target_x = self.pos_x
        self.bubble_until = 0.0
        self.bubble_pinned = False
        self._fade_started = None
        self._press_at = None
        self._long_fired = False
        self._focus = self._focus_key()
        self._blink_at = time.time() + random.uniform(2.0, 6.0)
        self._blinking_until = 0.0
        self._t0 = time.time()

        NSWorkspace.sharedWorkspace().notificationCenter().addObserver_selector_name_object_(
            self, "spaceChanged:", "NSWorkspaceActiveSpaceDidChangeNotification", None
        )

        threading.Thread(target=self._refresh_loop, daemon=True).start()
        return self

    # ---------- 창 ----------

    @objc.python_method
    def _build_windows(self) -> None:
        self.window = _new_window(self.size, self.size, NSFloatingWindowLevel)
        view = MascotView.alloc().initWithFrame_controller_(
            NSMakeRect(0, 0, self.size, self.size), self
        )
        self.window.setContentView_(view)
        self.view = view
        self.window.orderFrontRegardless()

        self.bubble_window = _new_window(260, 200, NSStatusWindowLevel)
        self.bubble_window.setIgnoresMouseEvents_(True)
        self.bubble_view = BubbleView.alloc().initWithFrame_(NSMakeRect(0, 0, 260, 200))
        self.bubble_window.setContentView_(self.bubble_view)

    @objc.python_method
    def _screen_bounds(self):
        """마스코트가 올라가 있는 화면의 영역.

        NSScreen.mainScreen() 은 키보드 포커스가 있는 화면을 가리킨다.
        그걸 기준으로 삼으면 다른 모니터를 클릭할 때마다 마스코트가
        따라 움직여 버리므로, 현재 좌표가 속한 화면을 직접 찾는다.
        """
        screens = NSScreen.screens()
        if self.pos_x is not None:
            for screen in screens:
                frame = screen.frame()
                if (
                    frame.origin.x <= self.pos_x < frame.origin.x + frame.size.width
                    and frame.origin.y <= self.pos_y < frame.origin.y + frame.size.height
                ):
                    return screen.visibleFrame()
        # 좌표가 어느 화면에도 없으면(모니터를 뽑았을 때 등) 주 화면으로 돌아온다
        screen = NSScreen.mainScreen() or screens[0]
        return screen.visibleFrame()

    @objc.python_method
    def _place_initial(self) -> None:
        frame = self._screen_bounds()
        saved = self.cfg["mascot"].get("position")
        if saved and len(saved) == 2:
            self.pos_x, self.pos_y = float(saved[0]), float(saved[1])
        else:
            self.pos_x = frame.origin.x + frame.size.width * 0.72
            self.pos_y = frame.origin.y + self.size * 0.45
        self._clamp()
        self._sync_window()

    @objc.python_method
    def _clamp(self) -> None:
        frame = self._screen_bounds()
        half = self.size / 2
        self.pos_x = max(frame.origin.x + half, min(frame.origin.x + frame.size.width - half, self.pos_x))
        self.pos_y = max(frame.origin.y + half * 0.6, min(frame.origin.y + frame.size.height - half, self.pos_y))

    @objc.python_method
    def _sync_window(self) -> None:
        """창을 정수 좌표에 붙인다.

        걷는 속도는 프레임당 1.5칸처럼 소수로 나오는데, 창이 소수점 위치에
        놓이면 macOS 가 내용을 다시 샘플링해서 도트가 흐려진다. 좌표 자체는
        실수로 두어 움직임은 매끄럽게 하고, 화면에 놓을 때만 반올림한다.
        """
        self.window.setFrameOrigin_(
            NSMakePoint(
                round(self.pos_x - self.size / 2),
                round(self.pos_y - self.size / 2),
            )
        )

    # ---------- 사용량 갱신 ----------

    @objc.python_method
    def _refresh_loop(self) -> None:
        while True:
            try:
                self.index.refresh()
                # 기준 금액은 매번 파일에서 다시 읽는다.
                # --calibrate 로 맞춘 값이 재시작 없이 반영되도록.
                self.cfg["block_cost_limit"] = config.load().get("block_cost_limit")
                self._pending = summarize(
                    self.index.entries,
                    self.cfg["block_hours"],
                    self.cfg.get("block_cost_limit"),
                )
            except Exception:  # 갱신 실패로 마스코트가 멈추면 안 된다
                pass
            self._refresh_now.wait(max(10, int(self.cfg["refresh_seconds"])))
            self._refresh_now.clear()

    @objc.python_method
    def _adopt_snapshot(self) -> None:
        pending, self._pending = self._pending, None
        if pending is None:
            return
        self.snapshot = pending
        self.state.mood = self._demo_mood() or pending.mood
        self.notifier.update(pending)
        if self.bubble_window.isVisible():
            self._render_bubble()

    # ---------- 애니메이션 ----------

    def tick_(self, _timer):
        now = time.time()
        self._adopt_snapshot()
        if self.force_mood == "cycle":
            self.state.mood = self._demo_mood()
        self._update_blink(now)
        self._update_walk(now)
        self._update_hover()

        sprite.step(self.state, now - self._t0)
        self.state.walking = self.walk_state == "walk"
        self.view.setNeedsDisplay_(True)
        self._sync_window()

        self._update_press(now)
        self._update_bubble(now)

    @objc.python_method
    def _demo_mood(self) -> str | None:
        """--demo 로 고정한 표정. cycle 이면 일정 간격으로 돌아간다."""
        if self.force_mood is None:
            return None
        if self.force_mood != "cycle":
            return self.force_mood
        index = int(time.time() / DEMO_SECONDS) % len(DEMO_CYCLE)
        return DEMO_CYCLE[index]

    @objc.python_method
    def _update_blink(self, now: float) -> None:
        if self.state.mood == "sleepy":
            self.state.blink = 0.0
            return
        if now >= self._blink_at:
            self._blinking_until = now + 0.12
            self._blink_at = now + random.uniform(2.5, 7.0)
        self.state.blink = 1.0 if now < self._blinking_until else 0.0

    @objc.python_method
    def _update_walk(self, now: float) -> None:
        # 잠깐 뜬 말풍선을 읽는 동안에는 멈춰 서고, 고정해 둔 동안에는 계속 돌아다닌다
        if self.state.dragging or (self.bubble_window.isVisible() and not self.bubble_pinned):
            self.walk_state = "idle"
            self.state_until = max(self.state_until, now + 1.0)
            return
        # 다 써 버려 누워 있는 동안에는 움직이지 않는다
        if not self.cfg["mascot"].get("wander", True) or self.state.mood == "exhausted":
            self.walk_state = "idle"
            return

        if self.walk_state == "idle":
            if now >= self.state_until:
                frame = self._screen_bounds()
                margin = self.size * 0.6
                self.target_x = random.uniform(
                    frame.origin.x + margin, frame.origin.x + frame.size.width - margin
                )
                if abs(self.target_x - self.pos_x) > 20:
                    self.walk_state = "walk"
            return

        delta = self.target_x - self.pos_x
        if abs(delta) < 2.0:
            self.walk_state = "idle"
            self.state_until = now + random.uniform(4.0, 12.0)
            self._save_position()
            return
        direction = 1 if delta > 0 else -1
        self.state.facing = direction
        self.pos_x += direction * self.speed * FRAME_INTERVAL
        self._clamp()

    @objc.python_method
    def _focus_key(self):
        """지금 포커스가 있는 화면을 구분하는 값. 바뀌면 말풍선을 닫는다."""
        screen = NSScreen.mainScreen()
        if screen is None:
            return None
        frame = screen.frame()
        return (frame.origin.x, frame.origin.y)

    @objc.python_method
    def _mouse_is_down(self) -> bool:
        return bool(NSEvent.pressedMouseButtons())

    @objc.python_method
    def _update_press(self, now: float) -> None:
        """꾹 누르고 있으면 말풍선을 고정해서 띄운다."""
        if self._press_at is None or self.state.dragging:
            return
        if not self._mouse_is_down():
            # mouseUp 을 놓친 경우에 대비한 안전장치
            self._press_at = None
            return
        if self._long_fired:
            return
        if now - self._press_at >= LONG_PRESS_SECONDS:
            self._long_fired = True
            self.show_bubble(pinned=True)

    @objc.python_method
    def _update_bubble(self, now: float) -> None:
        if self._fade_started is not None:
            progress = (now - self._fade_started) / FADE_SECONDS
            if progress >= 1.0:
                self.bubble_window.orderOut_(None)
                self.bubble_window.setAlphaValue_(1.0)
                self._fade_started = None
                self.bubble_until = 0.0
                self.bubble_pinned = False
            else:
                self.bubble_window.setAlphaValue_(1.0 - progress)
            return

        if not self.bubble_window.isVisible():
            return

        self._position_bubble()

        # 다른 모니터로 포커스가 옮겨가면 닫는다
        focus = self._focus_key()
        if focus != self._focus:
            self._focus = focus
            self.hide_bubble()
            return

        if self.bubble_until and now > self.bubble_until:
            self.hide_bubble()

    @objc.python_method
    def _update_hover(self) -> None:
        """마스코트 위에 있을 때만 마우스를 받아, 나머지 영역은 클릭이 통과하게 한다."""
        if self.state.dragging or self._press_at is not None:
            self.window.setIgnoresMouseEvents_(False)
            return
        location = NSEvent.mouseLocation()
        half_w, half_h = sprite.hit_extent(self.size)
        dx = abs(location.x - self.pos_x)
        dy = abs(location.y - self.pos_y)
        self.window.setIgnoresMouseEvents_(dx > half_w or dy > half_h)

    # ---------- 상호작용 ----------

    @objc.python_method
    def press_began(self) -> None:
        self._press_at = time.time()
        self._long_fired = False

    @objc.python_method
    def press_ended(self) -> None:
        self._press_at = None
        if self._long_fired:
            # 꾹 눌러서 이미 고정해 띄웠다. 손을 떼도 그대로 둔다.
            self._long_fired = False
            return
        self.toggle_bubble()

    @objc.python_method
    def begin_drag(self) -> None:
        self.state.dragging = True
        self._press_at = None
        self.hide_bubble()

    @objc.python_method
    def end_drag(self) -> None:
        self.state.dragging = False
        self._save_position()

    @objc.python_method
    def move_to(self, x: float, y: float) -> None:
        self.pos_x, self.pos_y = x, y
        self._clamp()
        self._sync_window()

    @objc.python_method
    def set_scale(self, value: float) -> None:
        """마스코트 크기를 바로 바꾼다. 다시 실행할 필요 없다."""
        value = max(0.4, min(3.0, float(value)))
        self.cfg["mascot"]["scale"] = value
        self.size = float(round(BASE_SIZE * value))

        frame = self.window.frame()
        self.window.setFrame_display_(
            NSMakeRect(round(frame.origin.x), round(frame.origin.y), self.size, self.size),
            True,
        )
        self.view.setFrame_(NSMakeRect(0, 0, self.size, self.size))
        self._clamp()
        self._sync_window()
        self.view.setNeedsDisplay_(True)
        if self.bubble_window.isVisible():
            self._position_bubble()
        try:
            config.save(self.cfg)
        except OSError:
            pass

    @objc.python_method
    def _save_position(self) -> None:
        self.cfg["mascot"]["position"] = [round(self.pos_x, 1), round(self.pos_y, 1)]
        try:
            config.save(self.cfg)
        except OSError:
            pass

    @objc.python_method
    def toggle_bubble(self) -> None:
        if self.bubble_window.isVisible() and self._fade_started is None:
            self.hide_bubble()
        else:
            self.show_bubble()

    @objc.python_method
    def show_bubble(self, pinned: bool = False) -> None:
        """pinned 면 시간이 지나도 닫히지 않는다 (꾹 누르기)."""
        self._refresh_now.set()
        self._render_bubble()
        self._position_bubble()
        self._fade_started = None
        self.bubble_window.setAlphaValue_(1.0)
        self.bubble_window.orderFrontRegardless()
        self.bubble_pinned = pinned
        self._focus = self._focus_key()
        seconds = float(self.cfg["mascot"].get("bubble_seconds") or 0)
        self.bubble_until = 0.0 if pinned or seconds <= 0 else time.time() + seconds

    @objc.python_method
    def hide_bubble(self) -> None:
        """바로 지우지 않고 투명해지면서 사라진다. 실제로 감추는 건 _update_bubble."""
        if not self.bubble_window.isVisible() or self._fade_started is not None:
            return
        self._fade_started = time.time()
        self.bubble_until = 0.0

    @objc.python_method
    def _render_bubble(self) -> None:
        rows = rows_from_snapshot(self.snapshot)
        width, height = measure(rows)
        self.bubble_window.setFrame_display_(
            NSMakeRect(
                self.bubble_window.frame().origin.x,
                self.bubble_window.frame().origin.y,
                width,
                height,
            ),
            False,
        )
        self.bubble_view.setFrame_(NSMakeRect(0, 0, width, height))
        self.bubble_view.setRows_(rows)

    @objc.python_method
    def _position_bubble(self) -> None:
        frame = self._screen_bounds()
        size = self.bubble_window.frame().size
        gap = max(6.0, sprite.cell_size(self.size) * 1.0)
        x = self.pos_x - size.width / 2
        y = self.pos_y + sprite.top_offset(self.size) + gap
        x = max(frame.origin.x + 6, min(frame.origin.x + frame.size.width - size.width - 6, x))
        if y + size.height > frame.origin.y + frame.size.height:
            y = self.pos_y - sprite.bottom_offset(self.size) - gap - size.height
        x, y = round(x), round(y)
        self.bubble_view.setTailOffset_(round(self.pos_x) - (x + size.width / 2))
        self.bubble_window.setFrameOrigin_(NSMakePoint(x, y))

    # ---------- 메뉴 ----------

    @objc.python_method
    def show_menu(self, event, view) -> None:
        menu = NSMenu.alloc().init()

        def item(title, selector, state=False):
            entry = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, selector, "")
            entry.setTarget_(self)
            if state:
                entry.setState_(1)
            menu.addItem_(entry)

        item("사용량 보기", "menuShow:")
        item("지금 새로고침", "menuRefresh:")
        menu.addItem_(NSMenuItem.separatorItem())

        size_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("크기", None, "")
        size_menu = NSMenu.alloc().init()
        current = float(self.cfg["mascot"].get("scale") or 1.0)
        for label, value in SCALES:
            entry = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                label, "menuSetScale:", ""
            )
            entry.setTarget_(self)
            entry.setRepresentedObject_(value)
            if abs(current - value) < 0.01:
                entry.setState_(1)
            size_menu.addItem_(entry)
        size_item.setSubmenu_(size_menu)
        menu.addItem_(size_item)

        item(
            "돌아다니기",
            "menuToggleWander:",
            state=bool(self.cfg["mascot"].get("wander", True)),
        )
        item(
            "로그인 시 자동 실행",
            "menuToggleAutostart:",
            state=autostart.is_enabled(),
        )
        item("설정 파일 열기", "menuOpenConfig:")
        menu.addItem_(NSMenuItem.separatorItem())
        item("종료", "menuQuit:")

        NSMenu.popUpContextMenu_withEvent_forView_(menu, event, view)

    def spaceChanged_(self, _note):
        self.hide_bubble()

    def menuShow_(self, _sender):
        self.show_bubble(pinned=True)

    def menuRefresh_(self, _sender):
        self._refresh_now.set()
        self.show_bubble(pinned=True)

    def menuSetScale_(self, sender):
        self.set_scale(sender.representedObject())

    def menuToggleWander_(self, _sender):
        self.cfg["mascot"]["wander"] = not self.cfg["mascot"].get("wander", True)
        config.save(self.cfg)

    def menuToggleAutostart_(self, _sender):
        autostart.toggle()

    def menuOpenConfig_(self, _sender):
        import subprocess

        subprocess.run(["open", str(config.ensure_file())], check=False)

    def menuQuit_(self, _sender):
        NSApp().terminate_(self)


def run(force_mood: str | None = None) -> None:
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)

    controller = BuddyController.alloc().init()
    if force_mood:
        controller.force_mood = force_mood
        controller.state.mood = force_mood
    timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
        FRAME_INTERVAL, controller, "tick:", None, True
    )
    # 메뉴가 열려 있는 동안에도 애니메이션이 멈추지 않게 한다.
    from Foundation import NSRunLoop, NSRunLoopCommonModes

    NSRunLoop.currentRunLoop().addTimer_forMode_(timer, NSRunLoopCommonModes)
    app.run()
