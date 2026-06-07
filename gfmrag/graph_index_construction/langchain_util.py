import os
from types import SimpleNamespace
from typing import Any

import requests
from langchain_community.chat_models import ChatLlamaCpp, ChatOllama
from langchain_nvidia_ai_endpoints import ChatNVIDIA
from langchain_openai import ChatOpenAI
from langchain_together import ChatTogether


class ChatOllamaNoThink:
    """Minimal Ollama chat client that disables "thinking" (``think=False``).

    Reasoning models such as Qwen3 emit long ``<think>`` chain-of-thought before
    answering, which is dramatically slower (≈18x in local tests) and unnecessary
    for extraction. langchain's ``ChatOllama`` wrappers can't toggle Ollama's
    top-level ``think`` field, and Qwen3's ``/no_think`` soft switch is ignored by
    some builds, so we call ``/api/chat`` directly. ``think=False`` is a no-op for
    non-reasoning models (e.g. Qwen2.5, Llama).

    Implements just the ``invoke(messages)`` interface the OpenIE/NER models use,
    returning an object with a ``.content`` attribute.
    """

    _ROLE = {"system": "system", "human": "user", "ai": "assistant"}

    def __init__(
        self,
        model: str,
        temperature: float = 0.0,
        num_ctx: int | None = None,
        think: bool = False,
        base_url: str | None = None,
        timeout: int = 600,
        **_: Any,
    ) -> None:
        self.model = model
        self.temperature = temperature
        self.num_ctx = num_ctx
        self.think = think
        self.timeout = timeout
        host = base_url or os.environ.get("OLLAMA_HOST", "127.0.0.1:11434")
        if not host.startswith("http"):
            host = f"http://{host}"
        self.url = host.rstrip("/") + "/api/chat"

    def invoke(self, messages: Any, **_: Any) -> SimpleNamespace:
        msgs = [
            {"role": self._ROLE.get(getattr(m, "type", "user"), "user"), "content": m.content}
            for m in messages
        ]
        options: dict[str, Any] = {"temperature": self.temperature}
        if self.num_ctx is not None:
            options["num_ctx"] = self.num_ctx
        body = {
            "model": self.model,
            "messages": msgs,
            "stream": False,
            "think": self.think,
            "options": options,
        }
        resp = requests.post(self.url, json=body, timeout=self.timeout)
        resp.raise_for_status()
        return SimpleNamespace(content=resp.json()["message"]["content"])


def init_langchain_model(
    llm: str,
    model_name: str,
    temperature: float = 0.0,
    max_retries: int = 5,
    timeout: int = 60,
    n_ctx: int | None = None,
    low_vram: bool = False,
    **kwargs: Any,
) -> ChatOpenAI | ChatTogether | ChatOllama | ChatLlamaCpp | ChatOllamaNoThink:
    """
    Initialize a language model from the langchain library.
    :param llm: The LLM to use, e.g., 'openai', 'together'
    :param model_name: The model name to use, e.g., 'gpt-3.5-turbo'
    """
    if llm == "openai":
        # https://python.langchain.com/v0.1/docs/integrations/chat/openai/

        assert model_name.startswith("gpt-")
        return ChatOpenAI(
            api_key=os.environ.get("OPENAI_API_KEY"),
            model=model_name,
            temperature=temperature,
            max_retries=max_retries,
            timeout=timeout,
            **kwargs,
        )
    elif llm == "nvidia":
        # https://python.langchain.com/docs/integrations/chat/nvidia_ai_endpoints/

        return ChatNVIDIA(
            nvidia_api_key=os.environ.get("NVIDIA_API_KEY"),
            base_url="https://integrate.api.nvidia.com/v1",
            model=model_name,
            temperature=temperature,
            **kwargs,
        )
    elif llm == "together":
        # https://python.langchain.com/v0.1/docs/integrations/chat/together/

        return ChatTogether(
            api_key=os.environ.get("TOGETHER_API_KEY"),
            model=model_name,
            temperature=temperature,
            **kwargs,
        )
    elif llm == "ollama":
        # https://python.langchain.com/v0.1/docs/integrations/chat/ollama/
        # Use ChatOllamaNoThink so reasoning models (e.g. Qwen3) answer without
        # emitting chain-of-thought (think=False) -- far faster, no-op otherwise.
        return ChatOllamaNoThink(
            model=model_name,  # e.g., 'qwen3:1.7b'
            temperature=temperature,
            num_ctx=n_ctx,
            **kwargs,
        )

    elif llm == "llama.cpp":
        # https://python.langchain.com/v0.2/docs/integrations/chat/llamacpp/
        llama_kwargs = {
            "model_path": model_name,  # model_name is the model path (gguf file)
            "temperature": temperature,
            "verbose": True,
        }

        if n_ctx is not None:
            llama_kwargs["n_ctx"] = n_ctx

        if low_vram:
            llama_kwargs["low_vram"] = True

        llama_kwargs.update(kwargs)

        return ChatLlamaCpp(**llama_kwargs)

    else:
        # add any LLMs you want to use here using LangChain
        raise NotImplementedError(f"LLM '{llm}' not implemented yet.")
