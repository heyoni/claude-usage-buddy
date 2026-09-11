#!/usr/bin/env bash
# 파이썬까지 통째로 넣은 독립 실행 앱을 만들고 zip 으로 묶는다.
# 결과: dist/Claude-Usage-Buddy-<버전>-<아키텍처>.zip
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PKG="$ROOT/packaging"
VENV="$ROOT/build/venv"

echo "==> 빌드용 가상환경"
python3 -m venv "$VENV"
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet "$ROOT" py2app

echo "==> 아이콘"
"$VENV/bin/python" -c "
from pathlib import Path
from buddy import appbundle
assert appbundle._build_icns(Path('$PKG/icon.icns')), 'iconutil 실패'
"

echo "==> py2app"
cd "$PKG"
rm -rf build dist
"$VENV/bin/python" setup.py py2app --quiet 2>&1 | grep -v "^$" | tail -3

VERSION="$("$VENV/bin/python" -c 'from buddy import __version__; print(__version__)')"
ARCH="$(uname -m)"
OUT="$ROOT/dist/Claude-Usage-Buddy-$VERSION-$ARCH.zip"
mkdir -p "$ROOT/dist"
rm -f "$OUT"

echo "==> zip"
# ditto 는 실행 권한과 번들 구조를 그대로 보존한다
ditto -c -k --keepParent "dist/Claude Usage Buddy.app" "$OUT"

echo
echo "완료: $OUT  ($(du -h "$OUT" | cut -f1))"
echo "앱:   $PKG/dist/Claude Usage Buddy.app"
