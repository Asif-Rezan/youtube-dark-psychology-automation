#!/usr/bin/env bash
set -euo pipefail
# Pin both inference code and the quantized weights for repeatable daily runs.
QWEN_RUNTIME_SHA=74bca3950054eed1795f525cb9cf06bfe796492d
QWEN_RUNTIME_DIR="${RUNNER_TEMP:-/tmp}/rezan-llama-${QWEN_RUNTIME_SHA}"
if [ ! -x "$QWEN_RUNTIME_DIR/build/bin/llama-server" ]; then
  git clone --filter=blob:none https://github.com/ggml-org/llama.cpp.git "$QWEN_RUNTIME_DIR"
  git -C "$QWEN_RUNTIME_DIR" checkout "$QWEN_RUNTIME_SHA"
  cmake -S "$QWEN_RUNTIME_DIR" -B "$QWEN_RUNTIME_DIR/build" -DGGML_CUDA=OFF -DLLAMA_CURL=OFF -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_EXAMPLES=OFF -DLLAMA_BUILD_SERVER=ON -DCMAKE_BUILD_TYPE=Release
  cmake --build "$QWEN_RUNTIME_DIR/build" --target llama-server -j 4
fi
QWEN_MODEL_PATH=$(python - <<'PY'
from huggingface_hub import hf_hub_download
print(hf_hub_download('unsloth/Qwen3.5-9B-GGUF', 'Qwen3.5-9B-Q4_K_M.gguf',
                     revision='3885219b6810b007914f3a7950a8d1b469d598a5'))
PY
)
nohup "$QWEN_RUNTIME_DIR/build/bin/llama-server" \
  --model "$QWEN_MODEL_PATH" --alias Qwen/Qwen3.5-9B \
  --host 127.0.0.1 --port 8080 --ctx-size 12288 --parallel 1 \
  --threads 4 --batch-size 256 --ubatch-size 128 --jinja \
  --chat-template-kwargs '{"enable_thinking":false}' \
  > "${RUNNER_TEMP:-/tmp}/rezan-qwen-server.log" 2>&1 &
QWEN_SERVER_PID=$!
echo "$QWEN_SERVER_PID" > "${RUNNER_TEMP:-/tmp}/rezan-qwen-server.pid"
python - <<'PY'
import time
import requests
for _ in range(180):
    try:
        if requests.get('http://127.0.0.1:8080/health', timeout=5).ok:
            print('Qwen3.5-9B CPU server ready on loopback')
            break
    except requests.RequestException:
        pass
    time.sleep(2)
else:
    raise SystemExit('Qwen server did not become ready; inspect the private runner log')
PY
