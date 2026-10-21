#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../desktop"
# Prerequisite: rustup target add wasm32-unknown-unknown
cargo build --locked --release --target wasm32-unknown-unknown -p gabbaproc-browser-parser
cp target/wasm32-unknown-unknown/release/gabbaproc_browser_parser.wasm ../web/assets/export-parser.wasm
