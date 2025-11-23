# forte-hackathon-core

GitLab Merge Request webhook that triggers an automated GPT code review and posts results back to the MR.

Important security note: do not hardcode tokens in code. Provide them via environment variables as described below.

## Setup

1) Create or use a GitLab Personal Access Token (PAT) with scopes:
- api

2) Create a Gemini API key (optional but recommended) and pick a model:
- Set `GEMINI_API_KEY`
- Optionally set `GEMINI_MODEL` (default: `gemini-1.5-flash`)

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
- `GEMINI_MODEL` (optional) — defaults to `gemini-1.5-flash`
- `HOST` (optional) — FastAPI bind address, default `0.0.0.0`
- `PORT` (optional) — FastAPI port, default `8080`

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
  - Posts a review comment back to the MR

## .env support

If a `.env` file is present, it will be loaded on startup. Example:

```env
GITLAB_TOKEN=glpat-xxxx
GITLAB_WEBHOOK_SECRET=supersecret
WEBHOOK_URL=https://your-url/gitlab/webhook
GEMINI_API_KEY=your-gemini-key
# GEMINI_MODEL=gemini-1.5-pro
```

## Security

- Never commit tokens to the repo.
- Rotate any token that was previously exposed.
- Use the `GITLAB_WEBHOOK_SECRET` to validate incoming webhook requests.

## Limitations and next steps

- Review is re-posted per MR event; deduplication/threading can be added if needed.
- Diff length is capped to avoid large payloads.
- You can refine prompts or add per-repo config as a future enhancement.
