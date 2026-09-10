"""엔트리 포인트.

    python -m buddy              마스코트 실행
    python -m buddy --cli        터미널에 사용량 출력
    python -m buddy --json       JSON 으로 출력 (다른 도구에 연결할 때)
    python -m buddy --install-agent / --uninstall-agent
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

    from . import single

    if not single.acquire():
        pid = single.running_pid()
        where = f" (PID {pid})" if pid else ""
        print(f"이미 마스코트가 떠 있습니다{where}. 한 마리만 실행됩니다.")
        return 0

    from .app import run

    run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
