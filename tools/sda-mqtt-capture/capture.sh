#!/usr/bin/env bash
#
# Starts mitmproxy with the MQTT decoder for the Deepal SDA broker.
#
# Usage:
#   ./capture.sh [output-dir]
#   MODE=proxy PORT=8080 ./capture.sh [output-dir]
#   RAW=1 ./capture.sh [output-dir]      # also write mqtt-raw.log (local only)
#   HTTP=0 ./capture.sh [output-dir]     # skip http-transcript.log
#
# Modes:
#   wireguard (default)  Intercept everything through the WireGuard app; works
#                        even when the MQTT client ignores the Wi-Fi proxy.
#   proxy                Regular HTTP proxy on PORT; simplest if the app honours
#                        the iOS Wi-Fi proxy setting.
#
# The output directory defaults to ./capture and receives:
#   mqtt-transcript.log  decoded frames with secrets, plate and location masked
#   http-transcript.log  allowlisted app HTTP calls, masked
#   mqtt-raw.log         raw hex per message (only with RAW=1; local only)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT_DIR="${1:-$SCRIPT_DIR/capture}"
MODE="${MODE:-wireguard}"
PORT="${PORT:-8080}"
RAW="${RAW:-0}"
HTTP="${HTTP:-1}"

if [[ "$RAW" == "1" ]]; then
  RAW_FLAG="true"
else
  RAW_FLAG="false"
fi
if [[ "$HTTP" == "0" ]]; then
  HTTP_FLAG="false"
else
  HTTP_FLAG="true"
fi

# The MQTT secretKey and the broker credentials never leave the tester's Mac:
# the addon decodes the encrypted sers payloads in memory and masks everything
# else before writing the shareable transcript.
DUMP_ARGS=(--set "mqtt_dump_raw=$RAW_FLAG" --set "mqtt_dump_http=$HTTP_FLAG")

if ! command -v mitmdump >/dev/null 2>&1; then
  echo "mitmdump not found. Install it first:"
  echo "  brew install mitmproxy        # or: pipx install mitmproxy"
  exit 1
fi

mkdir -p "$OUT_DIR"

case "$MODE" in
  wireguard)
    echo "WireGuard mode:"
    echo "  1. Import the configuration mitmproxy prints into the WireGuard iOS app."
    echo "  2. Activate the tunnel."
    echo "  3. Open https://mitm.it in Safari and install/trust the CA."
    echo "  4. Do one lock and one unlock in the Deepal app, then stop mitmdump (Ctrl-C)."
    exec mitmdump \
      --mode wireguard \
      -s "$SCRIPT_DIR/mqtt_dump.py" \
      --set "mqtt_dump_dir=$OUT_DIR" \
      "${DUMP_ARGS[@]}"
    ;;
  proxy)
    echo "Proxy mode:"
    echo "  1. Set the iPhone Wi-Fi proxy to this Mac, port $PORT."
    echo "  2. Open https://mitm.it in Safari and install/trust the CA."
    echo "  3. Do one lock and one unlock in the Deepal app, then stop mitmdump (Ctrl-C)."
    echo "  If the broker host never appears, retry with MODE=wireguard."
    exec mitmdump \
      --mode regular \
      --listen-port "$PORT" \
      -s "$SCRIPT_DIR/mqtt_dump.py" \
      --set "mqtt_dump_dir=$OUT_DIR" \
      "${DUMP_ARGS[@]}"
    ;;
  *)
    echo "unknown MODE=$MODE (use wireguard or proxy)" >&2
    exit 1
    ;;
esac
