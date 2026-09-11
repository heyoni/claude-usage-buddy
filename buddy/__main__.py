"""엔트리 포인트.

    claude-usage-buddy                 마스코트 실행
    claude-usage-buddy --cli           터미널에 사용량 출력
    claude-usage-buddy --json          JSON 으로 출력 (다른 도구에 연결할 때)
    claude-usage-buddy --calibrate 90  Claude Code 가 알려주는 실제 퍼센트에 눈금 맞추기
    claude-usage-buddy --demo <표정>   표정을 고정해서 확인
                                       (happy busy worried panic exhausted sleepy,
                                        cycle 을 주면 4초마다 차례로 돌아간다)
    claude-usage-buddy --install-agent / --uninstall-agent
                                       로그인 시 자동 실행 등록 / 해제

설치하지 않고 저장소 안에서 바로 돌릴 때는 `python -m buddy` 도 같습니다.
"""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    flag = args[0] if args else ""

    if flag in ("--cli", "-c"):
        from .cli import print_report

        print_report()
        return 0
    if flag == "--calibrate":
        from .cli import calibrate

        if len(args) < 2:
            print("사용법: python -m buddy --calibrate <퍼센트>")
            print("  예) Claude Code 가 90% 라고 하면:  python -m buddy --calibrate 90")
            return 1
        try:
            calibrate(float(args[1]))
        except ValueError:
            print("퍼센트는 숫자여야 합니다.")
            return 1
        return 0
    if flag == "--json":
        from .cli import print_json

        print_json()
        return 0
    if flag == "--install-agent":
        from . import autostart

        print(f"등록 완료: {autostart.enable()}")
        return 0
    if flag == "--uninstall-agent":
        from . import autostart

        autostart.disable()
        print("자동 실행 등록을 해제했습니다.")
        return 0
    if flag in ("-h", "--help"):
        print(__doc__)
        return 0

    if flag == "--demo":
        moods = ["happy", "busy", "worried", "panic", "exhausted", "sleepy", "cycle"]
        if len(args) < 2 or args[1] not in moods:
            print("사용법: python -m buddy --demo <표정>")
            print("  " + " | ".join(moods))
            return 1
        demo_mood = args[1]
    else:
        demo_mood = None

    from . import single

    if not single.acquire():
        pid = single.running_pid()
        where = f" (PID {pid})" if pid else ""
        print(f"이미 마스코트가 떠 있습니다{where}. 한 마리만 실행됩니다.")
        return 0

    from .app import run

    run(demo_mood)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
