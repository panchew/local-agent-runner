#!/usr/bin/env bash
# One-command §9 proof (CONTRACT.md §9, §10.3): build the image, then for each
# of three runs — reset the workspace from the pristine template, run the
# containerized CLI against live qwen2.5-coder:14b over HTTP, and mechanically
# check the transcript and workspace — stopping at the first failure
# ("three consecutive" is literal: after any failure the count restarts).
#
# Failed transcripts are kept under proof/artifacts/attempts/ (§6 cost
# visibility, honest evidence); converging transcripts land at
# proof/artifacts/transcript-run{1,2,3}.json (milestone artifacts).
#
# Usage: proof/run-proof.sh
#   OLLAMA_ENDPOINT  override the Ollama endpoint (default http://localhost:11434;
#                    the container uses --network host, the settled Linux default)
#   PROOF_MODEL      override the model tag (default qwen2.5-coder:14b)
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROOF_DIR="$REPO_ROOT/proof"
ENDPOINT="${OLLAMA_ENDPOINT:-http://localhost:11434}"
MODEL="${PROOF_MODEL:-qwen2.5-coder:14b}"
IMAGE="local-agent-runner-proof"
WORKSPACE="$PROOF_DIR/run-workspace"
ARTIFACTS="$PROOF_DIR/artifacts"

echo "== building $IMAGE =="
docker build -q -t "$IMAGE" -f "$PROOF_DIR/Dockerfile" "$REPO_ROOT"

mkdir -p "$ARTIFACTS/attempts"

fail() {
  local run="$1" reason="$2"
  local transcript="$ARTIFACTS/transcript-run$run.json"
  if [[ -f "$transcript" ]]; then
    local kept="$ARTIFACTS/attempts/attempt-$(date +%Y%m%dT%H%M%S)-run$run.json"
    mv "$transcript" "$kept"
    echo "run $run/3: FAIL ($reason) — transcript kept at ${kept#"$REPO_ROOT"/}"
  else
    echo "run $run/3: FAIL ($reason)"
  fi
  echo "PROOF: FAIL — fix, then rerun proof/run-proof.sh (the count of three restarts)"
  exit 1
}

for run in 1 2 3; do
  echo
  echo "== run $run/3 =="
  rm -rf "$WORKSPACE"
  cp -r "$PROOF_DIR/workspace-template" "$WORKSPACE"
  rm -f "$ARTIFACTS/transcript-run$run.json"

  docker run --rm --network host \
    --user "$(id -u):$(id -g)" \
    -v "$WORKSPACE:/work/workspace" \
    -v "$ARTIFACTS:/work/artifacts" \
    "$IMAGE" \
    --model "$MODEL" \
    --task /work/task.md \
    --tools /work/tools.json \
    --endpoint "$ENDPOINT" \
    --transcript "/work/artifacts/transcript-run$run.json" \
    || fail "$run" "CLI exit code $?"

  python3 "$PROOF_DIR/check_transcript.py" \
    "$ARTIFACTS/transcript-run$run.json" \
    --workspace "$WORKSPACE" \
    || fail "$run" "checker rejected the transcript"

  echo "run $run/3: PASS"
done

echo
echo "PROOF: PASS — 3/3 consecutive runs converged; transcripts in proof/artifacts/"
