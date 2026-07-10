# §10.3: the proof runs inside a container. Minimal image; the engine is
# installed from this repo checkout (no dev extras at proof time).
# Build context is the repo root: docker build -f proof/Dockerfile .
FROM python:3.12-slim

COPY pyproject.toml /opt/local-agent-runner/
COPY local_agent_runner/ /opt/local-agent-runner/local_agent_runner/
RUN pip install --no-cache-dir /opt/local-agent-runner

# The task and permissions are baked in; the workspace is mounted at
# /work/workspace by run-proof.sh, fresh from the template for every run
# (spec-settled). tools.json scopes allow_paths to /work/workspace/**.
COPY proof/task.md proof/tools.json /work/

# The CLI resolves relative tool paths and runs commands from the CWD, so the
# loop works inside the workspace the way the task wording assumes.
WORKDIR /work/workspace
ENTRYPOINT ["local-agent-runner"]
