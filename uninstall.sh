#!/usr/bin/env bash
# 자동 실행 등록과 명령 링크를 지우고 실행 중인 마스코트를 종료한다.
set -euo pipefail

VENV_DIR="$HOME/.claude-usage-buddy/venv"
BIN_DIR="$HOME/.local/bin"

if [[ -x "$VENV_DIR/bin/claude-usage-buddy" ]]; then
  "$VENV_DIR/bin/claude-usage-buddy" --uninstall-agent || true
fi
pkill -f "\-m buddy" 2>/dev/null || true
pkill -f "claude-usage-buddy" 2>/dev/null || true
rm -f "$BIN_DIR/claude-usage-buddy"

echo "정리했습니다."
echo "설정과 색인, 가상환경까지 지우려면:  rm -rf ~/.claude-usage-buddy"
