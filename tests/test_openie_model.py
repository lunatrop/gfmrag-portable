import os

import pytest

SAMPLE_TEXT = "Fred Gehrke\nClarence Fred Gehrke (April 24, 1918 \u2013 February 9, 2002) was an American football player and executive.\n He played in the National Football League (NFL) for the Cleveland / Los Angeles Rams, San Francisco 49ers and Chicago Cardinals from 1940 through 1950.\n To boost team morale, Gehrke designed and painted the Los Angeles Rams logo in 1948, which was the first painted on the helmets of an NFL team.\n He later served as the general manager of the Denver Broncos from 1977 through 1981.\n He is the great-grandfather of Miami Marlin Christian Yelich"


def test_llm_openie_model() -> None:
    import dotenv
    from hydra.utils import instantiate
    from omegaconf import OmegaConf

    cfg = OmegaConf.create(
        {
            "_target_": "gfmrag.graph_index_construction.openie_model.LLMOPENIEModel",
            "llm_api": "openai",
            "model_name": "gpt-4o-mini",
        }
    )

    dotenv.load_dotenv()

    openie_model = instantiate(cfg)
    res = openie_model(SAMPLE_TEXT)
    print(res)
    assert isinstance(res, dict)


def _ollama_available(host: str, model: str) -> bool:
    """Return True if an Ollama server at ``host`` has ``model`` available."""
    try:
        import requests

        tags = requests.get(f"{host}/api/tags", timeout=3).json()
        names = {m.get("name", "") for m in tags.get("models", [])}
        return any(n == model or n.startswith(f"{model}:") for n in names)
    except Exception:
        return False


def test_llm_openie_model_ollama() -> None:
    """OpenIE against a local Ollama backend.

    Skips unless an Ollama server is reachable and the model is pulled. Override
    via OLLAMA_HOST / OLLAMA_OPENIE_MODEL. Regression cover for the bare-array
    NER parsing that non-OpenAI backends emit.
    """
    from hydra.utils import instantiate
    from omegaconf import OmegaConf

    host = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
    if not host.startswith("http"):
        host = f"http://{host}"
    model = os.environ.get("OLLAMA_OPENIE_MODEL", "qwen2.5:3b")

    if not _ollama_available(host, model):
        pytest.skip(f"Ollama model '{model}' not available at {host}")

    cfg = OmegaConf.create(
        {
            "_target_": "gfmrag.graph_index_construction.openie_model.LLMOPENIEModel",
            "llm_api": "ollama",
            "model_name": model,
        }
    )

    openie_model = instantiate(cfg)
    res = openie_model(SAMPLE_TEXT)
    print(res)
    assert isinstance(res, dict)
    assert res["extracted_entities"], "NER returned no entities"
    assert res["extracted_triples"], "OpenIE returned no triples"


if __name__ == "__main__":
    test_llm_openie_model()
    test_llm_openie_model_ollama()
