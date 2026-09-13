import httpx

from . import config


class ProviderError(RuntimeError):
    pass


class Provider:
    def __init__(self, name=None, model=None):
        self.name = name or config.PROVIDER
        self.model = model or config.MODEL

    def check(self):
        if self.name == "gemini":
            if not config.GEMINI_API_KEY:
                raise ProviderError("GEMINI_API_KEY is missing. Configure it and restart.")
            return
        if self.name != "ollama":
            raise ProviderError("Select LLM_PROVIDER=ollama or gemini and restart.")
        try:
            response = httpx.get(f"{config.OLLAMA_HOST}/api/tags", timeout=3)
            response.raise_for_status()
            names = {model["name"] for model in response.json()["models"]}
            if self.model not in names and f"{self.model}:latest" not in names:
                raise ProviderError(f"Model not installed. Run ollama pull {self.model}.")
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError("Ollama is unavailable. Start Ollama and retry.") from exc

    def complete(self, system, user, schema):
        try:
            if self.name == "ollama":
                response = httpx.post(
                    f"{config.OLLAMA_HOST}/api/chat",
                    timeout=config.TIMEOUT,
                    json={
                        "model": self.model,
                        "stream": False,
                        "format": schema.model_json_schema(),
                        "options": {"temperature": 0, "num_ctx": 16384, "num_predict": 2400},
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": user},
                        ],
                    },
                )
                response.raise_for_status()
                text = response.json()["message"]["content"]
            elif self.name == "gemini" and config.GEMINI_API_KEY:
                from google import genai
                from google.genai import types

                options = types.HttpOptions(
                    timeout=int(config.TIMEOUT * 1000),
                    retry_options=types.HttpRetryOptions(attempts=1),
                )
                with genai.Client(api_key=config.GEMINI_API_KEY, http_options=options) as client:
                    response = client.models.generate_content(
                        model=self.model,
                        contents=user,
                        config={
                            "system_instruction": system,
                            "temperature": 0,
                            "response_mime_type": "application/json",
                            "response_json_schema": schema.model_json_schema(),
                        },
                    )
                text = response.text or ""
            else:
                raise ProviderError("Configure Ollama or a Gemini API key before analysis.")
            return schema.model_validate_json(text)
        except ProviderError:
            raise
        except Exception as exc:
            if self.name == "gemini":
                message = {
                    400: "Gemini rejected the request. Check the API key and model configuration.",
                    401: "Gemini authentication failed. Check the configured API key.",
                    403: "Gemini access was denied. Check the key's project and model permissions.",
                    404: "Gemini model not found. Configure an available model and restart.",
                    429: "Gemini quota or rate limit reached. Check AI Studio usage before retrying.",
                    503: "Gemini is temporarily unavailable. Retry analysis in a moment.",
                }.get(getattr(exc, "code", None))
                if message:
                    raise ProviderError(message) from exc
            raise ProviderError(
                "The model timed out, failed, or returned invalid output. Check the provider and retry."
            ) from exc


def provider_status():
    provider = Provider()
    try:
        provider.check()
        return {
            "ready": True,
            "provider": provider.name,
            "model": provider.model,
            "detail": "Local model available"
            if provider.name == "ollama"
            else "Key configured; connection checked during analysis",
        }
    except ProviderError as exc:
        return {
            "ready": False,
            "provider": provider.name,
            "model": provider.model,
            "detail": str(exc),
        }
