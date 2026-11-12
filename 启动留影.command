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
if ! .venv/bin/python -c 'import flask, PIL' >/dev/null 2>&1; then
  echo '首次启动：安装依赖（需要网络）…'
  .venv/bin/python -m pip install -r requirements.txt || { read -r -p '安装失败，按回车退出…'; exit 1; }
fi
if curl -fsS http://127.0.0.1:47321/api/session >/dev/null 2>&1; then
  open http://127.0.0.1:47321
  exit 0
fi
.venv/bin/python app.py
