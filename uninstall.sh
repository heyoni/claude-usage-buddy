#!/usr/bin/env bash
# 자동 실행 등록을 지우고 실행 중인 마스코트를 종료한다.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$HOME/.claude-usage-buddy/venv"

if [[ -x "$VENV_DIR/bin/python" ]]; then
  (cd "$PROJECT_DIR" && "$VENV_DIR/bin/python" -m buddy --uninstall-agent) || true
fi
pkill -f "\-m buddy" 2>/dev/null || true

echo "정리했습니다."
echo "설정과 색인까지 지우려면:  rm -rf ~/.claude-usage-buddy"
