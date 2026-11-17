#!/usr/bin/env bash
export PYTHONPATH="$(cd "$(dirname "$0")/.." && pwd)${PYTHONPATH:+:$PYTHONPATH}"
# One-command verification of a custom tool that calls an external service
# (examples/ticket_service/): security, idempotency, integrity.
#
#   1. Offline verification suite: tracked checks against a fake third-party
#      service over real HTTP, with the model scripted. Writes
#      verification-results.{json,md} and appends to history.jsonl.
#   2. Mutation check: disables each protection in the tool, one at a time,
#      and confirms the suite catches it. Writes mutation-results.{json,md}.
#   3. Optional live proof with a real Ollama model (LIVE=1). Writes
#      live-proof.json.
#
# Results land in proof/artifacts/custom-tools/ticket-service/.
#
# Usage: proof/run-custom-tool-verification.sh
#   LIVE=1            also run the live-model proof (needs Ollama)
#   OLLAMA_ENDPOINT   default http://localhost:11434
#   PROOF_MODEL       default qwen3-coder:30b
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$REPO_ROOT/proof/artifacts/custom-tools/ticket-service"
PY="${PYTHON:-python3}"
mkdir -p "$OUT"
cd "$REPO_ROOT"
status=0

echo "== 1/3 verification suite =="
"$PY" -m pytest -q -p no:cacheprovider tests/test_ticket_service_tool.py \
  --verification-report "$OUT" || status=1

echo
echo "== 2/3 mutation check =="
"$PY" proof/custom_tool_mutation_check.py "$OUT" || status=1

echo
if [[ "${LIVE:-0}" == "1" ]]; then
  echo "== 3/3 live proof (${PROOF_MODEL:-qwen3-coder:30b}) =="
  "$PY" examples/ticket_service/live_proof.py \
    --model "${PROOF_MODEL:-qwen3-coder:30b}" \
    --endpoint "${OLLAMA_ENDPOINT:-http://localhost:11434}" \
    --out "$OUT" || status=1
else
  echo "== 3/3 live proof: skipped (set LIVE=1 to run against Ollama) =="
fi

echo
if [[ $status -eq 0 ]]; then
  echo "VERIFICATION: PASS (results in ${OUT#"$REPO_ROOT"/})"
else
  echo "VERIFICATION: FAIL (see ${OUT#"$REPO_ROOT"/})"
fi
exit $status
