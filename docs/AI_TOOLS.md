# AI-assisted development

Codex assisted with product scoping, implementation, code review, debugging, tests, documentation, local browser checks and deployment verification. This included the FastAPI service, frontend, provider integration, retrieval and citation checks, and per-claim review workflow.

Ollama and Gemini are runtime providers for claim extraction and evidence comparison. They are separate from the development assistant. Bundled PDFs are real issuer documents; example claims are labelled test inputs and include deliberately altered or invented statements. Every new analysis calls the selected runtime model. There is no precomputed or simulated-success fallback.
