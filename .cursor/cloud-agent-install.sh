#!/usr/bin/env bash
# Idempotent Cloud Agent bootstrap: Python deps, then OCR CLI if missing.
# Delegation mode only: do not configure an OCR LLM provider or API key.
set -euo pipefail

pip install -r requirements.txt

if ! command -v npm >/dev/null 2>&1; then
  if [ -s "${NVM_DIR:-$HOME/.nvm}/nvm.sh" ]; then
    # shellcheck disable=SC1090
    . "${NVM_DIR:-$HOME/.nvm}/nvm.sh"
    nvm install --lts
  elif command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update -y
    sudo apt-get install -y nodejs npm
  else
    echo "cloud-agent-install: npm missing and no nvm/apt-get path for Node.js LTS" >&2
    exit 1
  fi
fi

if ! command -v ocr >/dev/null 2>&1; then
  npm install -g @alibaba-group/open-code-review
fi
