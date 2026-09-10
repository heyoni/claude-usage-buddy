#!/usr/bin/env bash
# 가상환경을 만들고 의존성을 설치한다. --autostart 를 붙이면 로그인할 때 자동으로 뜬다.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$HOME/.claude-usage-buddy/venv"

echo "==> 가상환경 준비: $VENV_DIR"
mkdir -p "$(dirname "$VENV_DIR")"
python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet -r "$PROJECT_DIR/requirements.txt"

if [[ "${1:-}" == "--autostart" ]]; then
  echo "==> 로그인 시 자동 실행 등록"
  (cd "$PROJECT_DIR" && "$VENV_DIR/bin/python" -m buddy --install-agent)
else
  echo
  echo "설치 완료. 실행:"
  echo "  cd $PROJECT_DIR && $VENV_DIR/bin/python -m buddy"
  echo
  echo "로그인할 때 자동으로 띄우려면:  ./install.sh --autostart"
fi
