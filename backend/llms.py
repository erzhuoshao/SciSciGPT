# All claude models: https://docs.anthropic.com/en/docs/about-claude/models
from langchain_google_vertexai.model_garden import ChatAnthropicVertex
from langchain_anthropic import ChatAnthropic


def load_llm(metadata: dict, **kwargs):
    model_name = metadata.get("model_name")
    if not model_name:
        raise ValueError("metadata.model_name is required")

    api_key = metadata.get("api_key")
    api_key = api_key if isinstance(api_key, str) else None

    if api_key:
        anthropic_model_config = {
            "api_key": api_key,
            "temperature": 0.0,
        }
        # Opus 4.7+ rejects temperature/top_p/top_k with a 400 error
        if model_name == "claude-opus-4.8":
            anthropic_model_config.pop("temperature")

        model_config = {
            "claude-opus-4.8": {
                "model_name": "claude-opus-4-8",
                "max_tokens": 64_000,
            },
            "claude-4.6": {
                "model_name": "claude-sonnet-4-6"
            },
        }

        if model_name not in model_config:
            raise ValueError(f"Unsupported model_name '{model_name}' for Anthropic")

        llm = ChatAnthropic(
            **model_config[model_name],
            **anthropic_model_config,
            **kwargs,
        )

    else:
        # Initialise the Model
        google_vertexai_model_config = {
            "project": "ksm-rch-sciscigpt",
            "location": "us-east5",
            "temperature": 0.0,
        }
        # Opus 4.7+ rejects temperature/top_p/top_k with a 400 error
        if model_name == "claude-opus-4.8":
            google_vertexai_model_config.pop("temperature")

        model_config = {
            "claude-opus-4.8": {
                "model_name": "claude-opus-4-8",
                "max_output_tokens": 64_000,
            },
            "claude-4.6": {
                "model_name": "claude-sonnet-4-6",
                "max_output_tokens": 64_000,
            },
        }

        if model_name not in model_config:
            raise ValueError(f"Unsupported model_name '{model_name}' for Vertex AI")

        llm = ChatAnthropicVertex(
            **model_config[model_name],
            **google_vertexai_model_config,
            **kwargs,
        )

    return llm
