#!/bin/bash
set -e
cd "$(dirname "$0")"
if ! command -v python3 >/dev/null 2>&1; then
  echo '请先从 https://www.python.org/downloads/ 安装 Python 3.9 或更高版本。'
  read -r -p '按回车退出…'
  exit 1
fi
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
fi
if ! .venv/bin/python -c 'import flask, PIL, webview' >/dev/null 2>&1; then
  echo '首次启动：安装依赖（需要网络）…'
  .venv/bin/python -m pip install -r requirements-desktop.txt || { read -r -p '安装失败，按回车退出…'; exit 1; }
fi
.venv/bin/python desktop.py
