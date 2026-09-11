#!/usr/bin/env bash
# 가상환경을 만들고 claude-usage-buddy 명령을 설치한다.
# --autostart 를 붙이면 로그인할 때 자동으로 뜬다.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$HOME/.claude-usage-buddy/venv"
BIN_DIR="$HOME/.local/bin"

echo "==> 가상환경 준비: $VENV_DIR"
mkdir -p "$(dirname "$VENV_DIR")"
python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet --editable "$PROJECT_DIR"

# PATH 에 있는 곳으로 이어 두면 어느 폴더에서든 이름만으로 실행된다
LINKED=""
if [[ ":$PATH:" == *":$BIN_DIR:"* ]] || [[ -d "$BIN_DIR" ]]; then
  mkdir -p "$BIN_DIR"
  ln -sf "$VENV_DIR/bin/claude-usage-buddy" "$BIN_DIR/claude-usage-buddy"
  LINKED="$BIN_DIR/claude-usage-buddy"
fi

if [[ "${1:-}" == "--autostart" ]]; then
  echo "==> 로그인 시 자동 실행 등록"
  "$VENV_DIR/bin/claude-usage-buddy" --install-agent
fi

echo
echo "설치 완료."
if [[ -n "$LINKED" ]]; then
  echo "  실행:  claude-usage-buddy"
  if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    echo
    echo "  ! $BIN_DIR 가 PATH 에 없습니다. 셸 설정에 아래 줄을 넣어 주세요:"
    echo "      export PATH=\"\$HOME/.local/bin:\$PATH\""
  fi
else
  echo "  실행:  $VENV_DIR/bin/claude-usage-buddy"
fi
echo
echo "로그인할 때 자동으로 띄우려면:  ./install.sh --autostart"
