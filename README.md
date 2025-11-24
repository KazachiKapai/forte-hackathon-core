# forte-hackathon-core

GitLab Merge Request webhook that triggers an automated GPT code review and posts results back to the MR.

Important security note: do not hardcode tokens in code. Provide them via environment variables as described below.

## Setup

1) Create or use a GitLab Personal Access Token (PAT) with scopes:
- api

2) Create a Gemini API key (optional but recommended) and pick a model:
- Set `GEMINI_API_KEY`
- Optionally set `GEMINI_MODEL` (default: `gemini-2.5-pro`)

3) Install dependencies:

```bash
pip install -r requirements.txt
```

## Environment variables

- `GITLAB_URL` (default: `https://gitlab.com`)
- `GITLAB_TOKEN` (required) — your GitLab PAT
- `GITLAB_WEBHOOK_SECRET` (required) — shared secret GitLab uses to sign webhook requests
- `WEBHOOK_URL` (required for hook registration) — public URL for your webhook endpoint, e.g. `https://your.domain/gitlab/webhook`
- `GEMINI_API_KEY` (optional) — enables GPT review via Gemini
- `GEMINI_MODEL` (optional) — defaults to `gemini-2.5-pro`
- `ENV` (optional) — `prod` or `dev`. In `dev`, Gemini is mocked:
  - Review: returns deterministic structured JSON inside the note
  - Tagging: heuristic selection from candidates without calling Gemini
- `LABEL_CANDIDATES` (optional) — comma-separated list of labels to auto-apply via Gemini, e.g. `bug,security,perf,refactor,docs`
- `LABEL_MAX` (optional) — maximum labels Gemini may apply (default: 2, cap: 5)
- `HOST` (optional) — FastAPI bind address, default `0.0.0.0`
- `PORT` (optional) — FastAPI port, default `8080`
- `WORKER_CONCURRENCY` (optional) — max concurrent MR processes (default: 4; min enforced: 2)
- `DEDUPE_TTL_SECONDS` (optional) — idempotency window for webhook dedup (default: 300)
- `IP_ALLOWLIST` (optional) — comma-separated CIDRs or IPs allowed to call the webhook (e.g., `35.231.145.0/24,34.74.226.50`)
- `AUTO_ALLOW_MY_IP` (optional) — if `true`, auto-detect and allow this machine's public IP
- `MY_PUBLIC_IP` (optional) — manual override for auto-detected public IP (used if `AUTO_ALLOW_MY_IP=true`)
- `RATE_LIMIT_PER_MIN` (optional) — per-IP requests per minute (default: 60)
- `RATE_LIMIT_BURST` (optional) — burst capacity for rate limiting (default: RATE_LIMIT_PER_MIN)
- `WORKER_CONCURRENCY` (optional) — max concurrent MR processes (default: 4; min enforced: 2)

Tip: For local development, expose your server with a tunnel (e.g., `ngrok http 8080`) and use the public URL as `WEBHOOK_URL`.

## Run the webhook server

```bash
export GITLAB_TOKEN=...           # required
export GITLAB_WEBHOOK_SECRET=...  # required
export GEMINI_API_KEY=...         # optional (enables AI review)
python main.py serve
```

The server provides:
- `POST /gitlab/webhook` — GitLab MR webhook endpoint
- `GET /health` — health check

## Register webhooks for your projects

Register MR webhooks for all projects where you have membership:

```bash
export GITLAB_TOKEN=...             # required
export GITLAB_WEBHOOK_SECRET=...    # required
export WEBHOOK_URL=https://.../gitlab/webhook
python main.py register-hooks
```

Or target specific projects by ID:

```bash
python main.py register-hooks --project-id 123 --project-id 456
```

## Integration testing helpers

List your membership projects (IDs and paths):

```bash
python main.py list-projects
```

Create a test MR in a specific project (branch + commit + MR):

```bash
python main.py test-mr --project-id 123 \
  --title "Webhook Test MR"
```

Options:
- `--branch` custom branch name (default: `test-webhook-<timestamp>`)
- `--file-path` file to create (default: `webhook_test.txt`)
- `--target-branch` override target (default: project default branch)

## What it does

- On MR events (open, reopen, update), the webhook:
  - Fetches the MR diffs via GitLab API
  - Optionally generates a GPT review using Gemini if `GEMINI_API_KEY` is set
  - Optionally classifies the MR into up to `LABEL_MAX` labels from `LABEL_CANDIDATES` and applies them
  - Posts a review comment back to the MR

## .env support

If a `.env` file is present, it will be loaded on startup. Example:

```env
GITLAB_TOKEN=glpat-xxxx
GITLAB_WEBHOOK_SECRET=supersecret
WEBHOOK_URL=https://your-url/gitlab/webhook
GEMINI_API_KEY=your-gemini-key
# GEMINI_MODEL=gemini-2.0-pro
```

## Security

- Never commit tokens to the repo.
- Rotate any token that was previously exposed.
- Use the `GITLAB_WEBHOOK_SECRET` to validate incoming webhook requests.

## Limitations and next steps

- Review is re-posted per MR event; deduplication/threading can be added if needed.
- Diff length is capped to avoid large payloads.
- You can refine prompts or add per-repo config as a future enhancement.

## Project structure (SOLID)

- `app/config/`: configuration and logging
  - `app/config/config.py`: loads env into `AppConfig` and helper `read_env`
  - `app/config/logging_config.py`: centralized logger configuration via `LOG_LEVEL`
- `app/vcs/base.py`: VCS abstraction interface.
- `app/vcs/gitlab_service.py`: GitLab implementation (projects, MR diffs, notes, hooks, test MR).
- `app/vcs/github_service.py`: GitHub skeleton implementation (future).
- `app/review/base.py`: `ReviewGenerator` interface.
- `app/review/gemini_review.py`: Gemini implementation with model discovery and fallbacks.
- `app/webhook/processor.py`: validates webhook token, queues and processes MR tasks
- `app/server/http.py`: FastAPI app wiring (routes)
- `app/infra/task_executor.py`: bounded global worker pool (`WORKER_CONCURRENCY`)
- `main.py`: thin CLI entrypoint (`serve`, `register-hooks`, `list-projects`, `test-mr`).

## Troubleshooting

- 404 on ngrok “POST /”: webhook URL must end with `/gitlab/webhook`.
- 401 Invalid webhook token: secret in GitLab Webhooks must equal `GITLAB_WEBHOOK_SECRET`.
- 404 project/MR: verify IDs exist and PAT has access (Developer+).
- Gemini model errors:
  - Set a supported model: `export GEMINI_MODEL=gemini-2.5-pro` (or run model listing below).
  - List available models for your key:

```bash
python - <<'PY'
import os, google.generativeai as genai
genai.configure(api_key=os.environ["GEMINI_API_KEY"])
models=[m.name for m in genai.list_models() if "generateContent" in getattr(m,"supported_generation_methods",[])]
print("\n".join(models))
PY
```

- Verbose logs:
  - `export LOG_LEVEL=DEBUG`
  - Server logs show Gemini availability, key presence, chosen model, and API errors.
