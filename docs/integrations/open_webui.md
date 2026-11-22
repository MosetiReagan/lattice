# 🔌 Connecting Lattice to Open WebUI & Developer Tools

Lattice exposes standard OpenAI-compatible `/v1/chat/completions` and `/v1/models` endpoints, making it a drop-in replacement for any client or web UI that supports local LLMs.

---

## 1. Quick Server Startup

Start Lattice with the `--preset chat` flag to automatically enable preemptive priority admission, continuous multi-slot batching, and auto-tuned host memory safety:

```bash
uv run --no-sync lattice serve \
  --model qwen2.5-0.5b-instruct-f16 \
  --preset chat \
  --host 127.0.0.1 \
  --port 8000
```

Verify that the server is online with `lattice status`:
```bash
uv run --no-sync lattice status
```

---

## 2. Connecting to Open WebUI

[Open WebUI](https://github.com/open-webui/open-webui) connects to Lattice as an OpenAI-compatible provider:

1. In Open WebUI, navigate to **Settings** > **Connections**.
2. Under **OpenAI API Connections**, click **Add Connection**:
   - **URL**: `http://127.0.0.1:8000/v1` *(or `http://host.docker.internal:8000/v1` if Open WebUI is running inside Docker)*.
   - **API Key**: `none` *(or your configured `LATTICE_API_KEY`)*.
3. Click **Save & Verify**.
4. Select `qwen2.5-0.5b-instruct-f16` from the model dropdown and start chatting.

---

## 3. Connecting to Continue.dev (VS Code / JetBrains)

Add the following to your `~/.continue/config.json`:

```json
{
  "models": [
    {
      "title": "Lattice Local (Qwen 2.5)",
      "provider": "openai",
      "model": "qwen2.5-0.5b-instruct-f16",
      "apiBase": "http://127.0.0.1:8000/v1",
      "apiKey": "none"
    }
  ]
}
```

---

## 4. Python Client (OpenAI SDK) with Priority Scheduling

Lattice supports the `priority` field in the request body. Priority `3` (interactive chat) will immediately preempt any low-priority background task (priority `0`):

```python
from openai import OpenAI

# Initialize standard OpenAI client pointed to Lattice
client = OpenAI(base_url="http://127.0.0.1:8000/v1", api_key="none")

# Stream interactive chat response (priority 3 preempts background batch jobs)
response = client.chat.completions.create(
    model="qwen2.5-0.5b-instruct-f16",
    messages=[
        {"role": "system", "content": "You are a concise engineering assistant."},
        {"role": "user", "content": "Explain preemption in 20 words."},
    ],
    extra_body={"priority": 3},  # High priority interactive query
    stream=True,
)

for chunk in response:
    content = chunk.choices[0].delta.content or ""
    print(content, end="", flush=True)
print()
```

---

## 5. cURL Testing

```bash
curl http://127.0.0.1:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen2.5-0.5b-instruct-f16",
    "messages": [
      {"role": "user", "content": "Say hello!"}
    ],
    "priority": 3,
    "stream": true
  }'
```
