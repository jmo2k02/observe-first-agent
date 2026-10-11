#!/usr/bin/env bash
# Seam B smoke test: bring the whole stack up and check that every part answers.
#
#   scripts/smoke.sh             health checks only (no API key used)
#   scripts/smoke.sh --real-run  also asks the agent one question with your key and checks that a trace arrives
#   scripts/smoke.sh --down      stop the stack afterwards (combine with --real-run if you like)
set -euo pipefail
cd "$(dirname "$0")/.."

REAL_RUN=false
DOWN=false
for arg in "$@"; do
  case "$arg" in
    --real-run) REAL_RUN=true ;;
    --down) DOWN=true ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

[ -f .env ] || { echo "FAIL: no .env file. Run: cp .env.example .env and add your OpenRouter key." >&2; exit 1; }
$DOWN && trap 'docker compose down' EXIT

echo "Starting the stack ..."
docker compose up -d --build

# wait_for NAME URL [TEXT]: poll URL for up to 120 s until it answers 200 (and contains TEXT, if given).
wait_for() {
  local name=$1 url=$2 text=${3:-}
  for _ in $(seq 1 60); do
    if body=$(curl -sf "$url" 2>/dev/null) && [[ -z "$text" || "$body" == *"$text"* ]]; then
      echo "ok    $name ($url)"
      return 0
    fi
    sleep 2
  done
  echo "FAIL  $name did not answer at $url. Check: docker compose logs" >&2
  exit 1
}

wait_for "helpdesk service health" http://localhost:8000/health '"ok"'
wait_for "Phoenix interface" http://localhost:6006 "Phoenix"
wait_for "Gradio chat interface" http://localhost:7860 "gradio"

# count_spans: how many lookup_employee tool spans Phoenix has stored so far.
count_spans() {
  curl -sf "http://localhost:6006/v1/projects/observe-first-agent/spans?limit=1000" | grep -o '"name":"lookup_employee"' | wc -l || true
}

if $REAL_RUN; then
  before=$(count_spans)
  echo "Asking the agent one question with the real model (uses your OpenRouter key) ..."
  event=$(curl -sf -X POST http://localhost:7860/gradio_api/call/_stream_response \
    -H 'Content-Type: application/json' -d '{"data": ["Who is employee E-102?"]}')
  event_id=$(echo "$event" | sed -E 's/.*"event_id": *"([^"]+)".*/\1/')
  # The answer streams back as server-sent events; wait until the run is finished.
  curl -sfN --max-time 180 "http://localhost:7860/gradio_api/call/_stream_response/$event_id" > /dev/null || true

  for _ in $(seq 1 30); do
    if [ "$(count_spans)" -gt "$before" ]; then
      echo "ok    a new trace with a lookup_employee tool span arrived in Phoenix"
      echo "PASS (open http://localhost:6006 to see it)"
      exit 0
    fi
    sleep 2
  done
  echo "FAIL  no new lookup_employee span in Phoenix. The model may be rate-limited: docker compose logs agent" >&2
  exit 1
fi

echo "PASS  chat http://localhost:7860, Phoenix http://localhost:6006, service http://localhost:8000/docs"
