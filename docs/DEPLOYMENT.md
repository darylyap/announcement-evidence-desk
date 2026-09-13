# Deploy to Vercel

The hosted application uses Gemini and persistent PostgreSQL. Docker and local Ollama are
not required by the hosted service.

## 1. Configure Gemini

Create an API key in [Google AI Studio](https://aistudio.google.com/apikey) using a project
with access to the selected model and sufficient quota. Keep the key out of source control.

For a local Gemini check, set these in `.env`:

```dotenv
LLM_PROVIDER=gemini
GEMINI_API_KEY=your-key
GEMINI_MODEL=gemini-3.6-flash
```

Restart `./run.sh`. Select Gemini in local Settings, then run:

```bash
.venv/bin/python scripts/check_app.py --provider gemini
```

To return to local Ollama, select Ollama in local Settings (or set the default `LLM_PROVIDER=ollama` and restart). No application code changes
are needed. This application uses the Gemini API, not Vertex AI.

## 2. Create the Vercel project and database

Import this repository into Vercel, using its root as the project root. FastAPI is configured
in `pyproject.toml`; `vercel.json` sets the function duration to 300 seconds. Enable Fluid Compute.

Connect a PostgreSQL database through the project's Storage/Marketplace integration, for
example Neon. Use its pooled PostgreSQL connection string as `DATABASE_URL`. If the integration
uses a prefixed variable name, also configure the unprefixed `DATABASE_URL` used by this app.
Use the provider's TLS-enabled connection string. Tables are created when the app starts.

The local SQLite file is excluded from deployment. It is not persistent storage on Vercel.

## 3. Configure environment variables

Set these in Vercel for the deployment environment:

| Variable | Value |
|---|---|
| `LLM_PROVIDER` | `gemini` |
| `GEMINI_API_KEY` | Your Gemini API key |
| `GEMINI_MODEL` | `gemini-3.6-flash`, or an available compatible model |
| `DATABASE_URL` | Persistent PostgreSQL connection string |
| `APP_ACCESS_KEY` | A strong random reviewer workspace key |

Generate a key locally with `python3.12 -c 'import secrets; print(secrets.token_urlsafe(32))'`.
Share the workspace key privately with the evaluator; do not send your Gemini or database
credentials. The app refuses hosted startup if required configuration is missing.

Deploy from Vercel, or use `npx vercel --prod` after CLI authentication and project linking.
Use the production URL that reviewers can reach. Check whether Vercel Deployment Protection
requires additional access and configure an appropriate reviewer-access path.

## 4. Verify the actual deployment

Set `APP_ACCESS_KEY` in your local `.env` to the hosted workspace key for this check:

```bash
.venv/bin/python scripts/check_app.py --url https://YOUR-PROJECT.vercel.app --require-hosted
```

Then verify in a browser: enter the workspace key, create a review, upload a PDF, run analysis,
inspect the actual PDF page, save and revise a separate assessment for each claim, set a review queue, and copy the brief. Reload the page
and confirm the saved data remains. Redeploy and confirm it still remains in PostgreSQL.

Keep the Vercel project, database and Gemini project available while the application is in use.
Monitor provider quota and deployment errors. Do not remove the database or rotate the
reviewer's access key without communicating the replacement.

## Troubleshooting

| Problem | Check |
|---|---|
| App fails to start | Required environment variables, PostgreSQL connectivity and Gemini selection |
| Workspace returns 401 | Enter the correct `APP_ACCESS_KEY` in Settings |
| Model failure | Key validity, model access, quota and provider availability; retry explicitly |
| PDF rejected | PDF at most 4 MB / 40 pages; DOCX, TXT and MD also supported; scans require extracted text |
| Interrupted analysis | Reopen the review; interrupted runs become retryable after five minutes |
| Reviewer cannot open URL | Production deployment and Vercel access settings |

References: [FastAPI on Vercel](https://vercel.com/docs/frameworks/backend/fastapi),
[Vercel limits](https://vercel.com/docs/functions/limitations),
[Gemini API keys](https://ai.google.dev/gemini-api/docs/api-key),
[Gemini structured output](https://ai.google.dev/gemini-api/docs/structured-output).

Bundled source PDFs in `examples/` must be included in the deployment. Uploaded originals are stored in PostgreSQL, not the function filesystem. Additive tables are created at startup; existing reviews retain their history. Redeployment does not reset data. Workspaces share the same access key.


## Reset the shared workspace

Only run this when you intend to clear all reviews and custom workspaces. The command exports records and retained source files to a private ZIP before deleting anything. It leaves General and Source examples, with one DBS two-claim review ready to analyse. It does not change credentials or the bundled example library. A backup is an export for recovery, not an in-app undo action.

```bash
# Local
.venv/bin/python scripts/reset_workspace.py --confirm-reset 127.0.0.1:8012 --backup-dir ../private-backups
# Hosted: APP_ACCESS_KEY must match the hosted workspace key
.venv/bin/python scripts/reset_workspace.py --url https://announcement-evidence-desk.vercel.app --confirm-reset announcement-evidence-desk.vercel.app --backup-dir ../private-backups
```

The exact hostname confirmation and a backup directory outside the public repository are required. Active analyses block the reset. Complete live verification before resetting, so test records do not remain in the evaluator's workspace.
