# tests/test_mcp_tools.py
"""Unit and Mock Contract Tests for the Model Context Protocol (MCP) Server.

Validates:
1. Registration and schema contract for MCP tools: gfm_retrieve, gfm_answer, gfm_status.
2. Formatted markdown output synthesis from backend JSON responses.
3. Resilient error handling (network timeouts, empty graphs, malformed payloads).
4. IAM token minting and caching behavior (preventing redundant subprocess spawns).
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

import scripts.mcp.gfmrag_server as mcp_server


# =====================================================================
# 1. Tool Registration & Schema Tests
# =====================================================================

def test_mcp_tools_are_registered() -> None:
    """Verifies that all three core GFM-RAG tools are registered with FastMCP."""
    tool_names = [tool.name for tool in mcp_server.mcp._tool_manager.list_tools()]
    assert "gfm_retrieve" in tool_names
    assert "gfm_answer" in tool_names
    assert "gfm_status" in tool_names


# =====================================================================
# 2. Token Caching Contract Tests
# =====================================================================

def test_token_caching_avoids_repeated_subprocess_calls() -> None:
    """_token() must cache the IAM identity token and avoid redundant gcloud subprocesses."""
    # Reset token cache
    mcp_server._tok["v"] = None
    mcp_server._tok["exp"] = 0.0

    mock_token_value = "header.payload.signature"

    with patch("subprocess.check_output", return_value=mock_token_value) as mock_cmd:
        # First call: should run subprocess
        t1 = mcp_server._token()
        assert t1 == mock_token_value
        assert mock_cmd.call_count == 1

        # Second call within validity window: should return cached value without subprocess
        t2 = mcp_server._token()
        assert t2 == mock_token_value
        assert mock_cmd.call_count == 1  # Still 1


# =====================================================================
# 3. gfm_retrieve Contract & Output Formatting Tests
# =====================================================================

def test_gfm_retrieve_formats_ranked_results_cleanly() -> None:
    """gfm_retrieve parses backend items and formats clean markdown blocks with scores."""
    mock_response = {
        "document": [
            {
                "id": "doc_101",
                "score": 0.887,
                "attributes": {"content": "Woolworths Modern Slavery Statement 2024 supply chain excerpt..."},
            },
            {
                "id": "doc_102",
                "score": -0.123,
                "attributes": {"content": "Secondary audit statement..."},
            },
        ]
    }

    with patch.object(mcp_server, "_post", return_value=mock_response) as mock_post:
        result = mcp_server.gfm_retrieve("Woolworths supply chain", top_k=2)

        mock_post.assert_called_once_with(
            "/retrieve",
            {"query": "Woolworths supply chain", "top_k": 2, "target_types": ["document"]},
        )
        assert "## document (top 2)" in result
        assert "[+0.89] doc_101" in result
        assert "[-0.12] doc_102" in result
        assert "Woolworths Modern Slavery Statement" in result


def test_gfm_retrieve_handles_empty_results() -> None:
    """gfm_retrieve returns '(no results)' when graph retrieval returns empty collections."""
    with patch.object(mcp_server, "_post", return_value={"document": []}):
        result = mcp_server.gfm_retrieve("nonexistent entity query")
        assert result == "(no results)"


def test_gfm_retrieve_handles_custom_target_types() -> None:
    """gfm_retrieve respects explicit target_types (e.g. ['entity', 'document'])."""
    mock_response = {
        "entity": [{"id": "BHP Group", "score": 1.25, "attributes": {"abn": "49004028077"}}]
    }

    with patch.object(mcp_server, "_post", return_value=mock_response) as mock_post:
        result = mcp_server.gfm_retrieve("BHP", target_types=["entity"])
        mock_post.assert_called_once_with(
            "/retrieve",
            {"query": "BHP", "top_k": 8, "target_types": ["entity"]},
        )
        assert "## entity (top 1)" in result
        assert "[+1.25] BHP Group" in result


# =====================================================================
# 4. gfm_answer Tests
# =====================================================================

def test_gfm_answer_returns_synthesized_response() -> None:
    """gfm_answer returns the LLM synthesis string from the service."""
    with patch.object(mcp_server, "_post", return_value={"answer": "Woolworths identifies tier-1 risks in seafood."}):
        ans = mcp_server.gfm_answer("What are tier-1 risks for Woolworths?", top_k=4)
        assert ans == "Woolworths identifies tier-1 risks in seafood."


def test_gfm_answer_falls_back_on_missing_answer_field() -> None:
    """gfm_answer returns fallback when answer field is absent in response."""
    with patch.object(mcp_server, "_post", return_value={}):
        ans = mcp_server.gfm_answer("query")
        assert ans == "(no answer)"


# =====================================================================
# 5. gfm_status Tests
# =====================================================================

def test_gfm_status_reports_ready_and_configured_dataset() -> None:
    """gfm_status queries /ready endpoint and includes the active dataset label."""
    mock_ready_json = json.dumps({"status": "ready", "colbert_index_loaded": True}).encode()

    mock_resp = MagicMock()
    mock_resp.read.return_value = mock_ready_json
    mock_resp.__enter__.return_value = mock_resp

    with patch.object(mcp_server, "_token", return_value="fake-token"), \
         patch("urllib.request.urlopen", return_value=mock_resp):
        status_str = mcp_server.gfm_status()
        status_data = json.loads(status_str)

        assert status_data["status"] == "ready"
        assert status_data["colbert_index_loaded"] is True
        assert status_data["configured_dataset"] == mcp_server.DATASET


def test_gfm_status_handles_service_error_gracefully() -> None:
    """gfm_status returns a structured JSON error string on network failure."""
    with patch.object(mcp_server, "_token", side_effect=RuntimeError("gcloud auth failed")):
        status_str = mcp_server.gfm_status()
        status_data = json.loads(status_str)
        assert "error" in status_data
        assert "gcloud auth failed" in status_data["error"]
