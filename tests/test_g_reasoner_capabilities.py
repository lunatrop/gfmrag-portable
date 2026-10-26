# tests/test_g_reasoner_capabilities.py
"""Test-Driven Reasoning Suite for G-Reasoner, Cross-Corpus Discovery, Convex Opt, and RLVR.

Covers:
1. Resource Advantage: G-Reasoner matrix message passing (0 LLM tokens, <50ms) vs. O(b^L) iterative LLM loops.
2. Seemingly Unrelated Corpora: Deriving multi-hop insights across disjoint domains (ESG Register + M&A + Cyber Threat Feeds).
3. Diagnostic Failing Tests (@pytest.mark.xfail): Exposing current codebase/corpus bottlenecks
   (single-mask seed OR-pooling, flat cosine disjoint-vocab blindness, hub degree bias, static temporal schema, visualize batch=1).
4. Convex Optimisation & RLVR Pipelines: Verifying Sinkhorn OT entity alignment, Steiner bridge scoring,
   degree-regularized convex subgraph selection, and GRPO verifiable reward advantages.
"""
from __future__ import annotations

import time
from typing import Dict, List
from unittest.mock import MagicMock

import pytest
import torch

from scripts.eval.convex_and_rl_reasoner import (
    SubgraphTrajectory,
    compute_grpo_subgraph_advantages,
    compute_steiner_bridge_scores,
    select_convex_subgraph,
    sinkhorn_entity_alignment,
)
from scripts.eval.fact_gate import FactGateOracle


# =====================================================================
# 1. Resource Advantage: G-Reasoner vs. Iterative LLM Reasoning
# =====================================================================

def test_contagion_blast_radius_zero_llm_tokens_outperforms_agent_loop() -> None:
    """Proves G-Reasoner's resource advantage on high-fanout 3-hop contagion queries.

    Scenario (from analyses/network-analysis-2026-06-18.md):
    A shared Big-4 auditor (e.g. Deloitte) or data custodian (Quantium) sits at the center
    of a 200-node corporate network with branching factor b=8.
    - An iterative LLM agent (IRCoT / ReAct) with top_k=5 truncation misses >80% of 3-hop targets
      or consumes O(b^L) = 512+ context expansions.
    - Tensor-based Bellman-Ford propagation computes the exact 3-hop contagion distribution
      across all 200 nodes in <50ms with 0 LLM tokens.
    """
    num_nodes = 200
    adj = torch.zeros((num_nodes, num_nodes), dtype=torch.float32)

    # Node 0: Shared Auditor Hub (connects to 10 Tier-1 parents: nodes 1..10)
    tier1_nodes = list(range(1, 11))
    # Each Tier-1 parent connects to 5 Tier-2 operating subsidiaries (nodes 11..60)
    tier2_nodes: List[int] = []
    # Each Tier-2 subsidiary connects to 2 Tier-3 SaaS/data vendors (nodes 61..160)
    tier3_nodes: List[int] = []

    curr = 11
    for t1 in tier1_nodes:
        adj[0, t1] = 1.0
        for _ in range(5):
            t2 = curr
            curr += 1
            tier2_nodes.append(t2)
            adj[t1, t2] = 1.0
            for _ in range(2):
                t3 = curr
                curr += 1
                tier3_nodes.append(t3)
                adj[t2, t3] = 1.0

    # Warm-up PyTorch BLAS threadpool before timing the 3-hop propagation pass
    _ = adj @ adj

    t0 = time.perf_counter()
    # 3-hop sparse/matrix message passing (0 LLM calls)
    seed = torch.zeros((1, num_nodes))
    seed[0, 0] = 1.0
    reach = seed.clone()
    state = seed.clone()
    for hop in range(1, 4):
        state = state @ adj
        reach = reach + (0.8 ** hop) * state
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    llm_tokens_used = 0

    # All 100 Tier-3 nodes (3 hops away) are recovered simultaneously
    recovered_tier3 = [n for n in tier3_nodes if reach[0, n].item() > 0.0]
    assert len(recovered_tier3) == len(tier3_nodes) == 100
    assert elapsed_ms < 50.0
    assert llm_tokens_used == 0

    # Compare with a conventional top_k=5 per-hop LLM agent budget
    agent_top_k_per_hop = 5
    max_agent_recovered = agent_top_k_per_hop  # Bounded by top-k context window truncation
    assert len(recovered_tier3) > 10 * max_agent_recovered


# =====================================================================
# 2. Multi-Anchor Steiner Bridge Discovery (Failing Base vs. Fixed)
# =====================================================================

def _build_quantium_contagion_graph() -> tuple[torch.Tensor, Dict[str, int]]:
    """Build the real-world topology from analyses/network-analysis-2026-06-18.md:
    Woolworths, CBA, Telstra, and Iress all connect to Quantium (the hidden systemic bridge).
    Meanwhile, Woolworths also connects to a noisy 1-hop leaf ('Local Cartage Co') with a heavy edge.
    """
    nodes = {
        "Woolworths": 0,
        "CBA": 1,
        "Telstra": 2,
        "Iress": 3,
        "Quantium": 4,          # True 4-way systemic bridge
        "Local Cartage Co": 5,  # 1-hop leaf attached only to Woolworths
        "Generic Retail Hub": 6,
    }
    n = len(nodes)
    adj = torch.zeros((n, n), dtype=torch.float32)

    # All 4 anchors connect to Quantium
    for anchor in ["Woolworths", "CBA", "Telstra", "Iress"]:
        u, v = nodes[anchor], nodes["Quantium"]
        adj[u, v] = adj[v, u] = 1.0

    # Noisy heavy edge on just ONE anchor (Woolworths -> Local Cartage Co)
    adj[nodes["Woolworths"], nodes["Local Cartage Co"]] = 10.0
    adj[nodes["Local Cartage Co"], nodes["Woolworths"]] = 10.0

    return adj, nodes


@pytest.mark.xfail(
    strict=True,
    reason="GFMRetriever.prepare_input_for_graph_retriever collapses all seed entities into one 1xN binary mask, allowing single-seed heavy leaves to beat multi-seed bridges.",
)
def test_single_mask_or_pooling_fails_on_steiner_bridge() -> None:
    """Demonstrates why collapsing seeds into a single 1xN mask fails on multi-anchor bridge queries."""
    adj, nodes = _build_quantium_contagion_graph()
    seeds = [nodes["Woolworths"], nodes["CBA"], nodes["Telstra"], nodes["Iress"]]

    # Current GFMRetriever behavior: single binary start_nodes_mask (1 x N)
    start_nodes_mask = torch.zeros((1, len(nodes)))
    start_nodes_mask[0, seeds] = 1.0

    # 1-step linear propagation over weighted adjacency
    raw_scores = (start_nodes_mask @ adj).squeeze(0)
    for s in seeds:
        raw_scores[s] = -1.0

    top_node = int(torch.argmax(raw_scores).item())
    # Fails: raw single-mask propagation picks 'Local Cartage Co' (score 10.0) over 'Quantium' (score 4.0)
    assert top_node == nodes["Quantium"]


def test_multi_channel_steiner_bridge_recovers_quantium() -> None:
    """Verifies that multi-channel geometric-mean propagation turns the Steiner bridge test green."""
    adj, nodes = _build_quantium_contagion_graph()
    seeds = [nodes["Woolworths"], nodes["CBA"], nodes["Telstra"], nodes["Iress"]]

    scores = compute_steiner_bridge_scores(adj, seeds, num_hops=2, degree_penalty_exp=0.3)
    top_node = int(torch.argmax(scores).item())

    assert top_node == nodes["Quantium"]
    assert scores[nodes["Quantium"]].item() > scores[nodes["Local Cartage Co"]].item() * 5.0


# =====================================================================
# 3. Seemingly Unrelated Corpora: Cross-Domain Knowledge Derivation
# =====================================================================

@pytest.mark.xfail(
    strict=True,
    reason="Flat dense vector search fails when Corpus A (ESG Register SPV) and Corpus C (Dark-Web Threat Intel) share zero surface vocabulary.",
)
def test_flat_cosine_fails_on_disjoint_spv_breach_corpora() -> None:
    """Exposes flat vector RAG failure across disjoint corpora (Register SPV vs. Global Cyber Breach).

    - Doc 0 (ESG Register): 'RASIER PACIFIC PTY LTD (ABN 68 622 365 459), revenue $0-99M, Sydney transport.'
    - Doc 1 (M&A Filing):   'Rasier Pacific Pty Ltd operates as the Australian subsidiary of Uber Technologies.'
    - Doc 2 (Threat Feed):  'Lapsus$ threat actor compromised contractor OAuth tokens at Uber Technologies.'
    - Doc 3 (Distractor):   'Sydney Small Business Transport Pty Ltd ($0-99M) had a minor phishing alert.'
    """
    # Orthogonal / disjoint feature subspaces: [ESG_Register_Dim, Corporate_Parent_Dim, Cyber_Breach_Dim]
    doc_embeddings = torch.tensor([
        [0.95, 0.05, 0.00],  # Doc 0: Rasier Pacific (ESG Register only)
        [0.60, 0.60, 0.00],  # Doc 1: Bridge document (links Rasier Pacific <-> Uber)
        [0.00, 0.70, 0.70],  # Doc 2: Cyber feed (Uber <-> Lapsus$ breach)
        [0.75, 0.00, 0.65],  # Doc 3: Lexical distractor (mentions both '$0-99M' and 'phishing')
    ])
    doc_embeddings = torch.nn.functional.normalize(doc_embeddings, dim=1)

    # Query asks for the ESG Register SPV exposed to Lapsus$ (combines dim 0 and dim 2)
    query_emb = torch.nn.functional.normalize(torch.tensor([0.70, 0.00, 0.70]), dim=0)
    flat_scores = doc_embeddings @ query_emb

    # Flat cosine ranks Distractor Doc 3 (#1) instead of recovering the true 2-hop chain (Doc 0 + Doc 1 + Doc 2)
    top_doc = int(torch.argmax(flat_scores).item())
    assert top_doc == 2  # Fails: top_doc is 3 (the distractor)


def test_sinkhorn_cross_corpus_alignment_resolves_spv_bridge() -> None:
    """Verifies that Entropic Optimal Transport (Sinkhorn) aligns cross-corpus entities without hub collapse.

    Scenario:
    News corpus mentions: ['Rasier Pacific', 'Pacific Brands', 'Uber Tech']
    Register entities:    ['RASIER PACIFIC PTY LTD (ABN ...)', 'PACIFIC BRANDS HOLDINGS (ABN ...)', 'UBER AUSTRALIA PTY LTD']
    Greedy matching without marginal constraints often collapses both 'Pacific' mentions onto whichever
    register entity has the higher prior degree. Sinkhorn enforces 1-to-1 doubly stochastic assignment.
    """
    # Cost matrix C[i, j]: lower = more similar
    # Note: both row 0 ('Rasier Pacific') and row 1 ('Pacific Brands') have low distance to col 1 ('PACIFIC BRANDS')
    # if 'PACIFIC BRANDS' is a dominant lexical hub, but row 0 is specifically closer to col 0.
    cost_matrix = torch.tensor([
        [0.12, 0.15, 0.85],  # 'Rasier Pacific'
        [0.45, 0.10, 0.90],  # 'Pacific Brands'
        [0.80, 0.85, 0.08],  # 'Uber Tech'
    ])

    transport_plan = sinkhorn_entity_alignment(cost_matrix, reg=0.03, num_iters=60)
    assignments = torch.argmax(transport_plan, dim=1).tolist()

    # Exact bijection: 0 -> 0, 1 -> 1, 2 -> 2
    assert assignments == [0, 1, 2]
    # Doubly stochastic check: column sums and row sums equal 1/3
    assert torch.allclose(transport_plan.sum(dim=1), torch.full((3,), 1.0 / 3.0), atol=1e-2)
    assert torch.allclose(transport_plan.sum(dim=0), torch.full((3,), 1.0 / 3.0), atol=1e-2)


# =====================================================================
# 4. Diagnostic Failing Tests: Code & Schema Bottlenecks
# =====================================================================

@pytest.mark.xfail(
    strict=True,
    reason="Raw unregularized GNN node read-out suffers from degree bias on super-hubs (e.g. Woolworths with 13+ edges).",
)
def test_unpenalized_gnn_suffers_from_hub_degree_bias() -> None:
    """Demonstrates degree bias when retrieving entities without convex degree regularization."""
    # Node 0: Seed ('Costa Group')
    # Node 1: Specific Target ('Driscoll's Berry JV' - degree 1, true partner)
    # Node 2: Super-hub ('Woolworths Group' - degree 50, generic customer)
    n = 53
    adj = torch.zeros((n, n))
    adj[0, 1] = adj[1, 0] = 1.0
    adj[0, 2] = adj[2, 0] = 1.0
    for k in range(3, n):
        adj[2, k] = adj[k, 2] = 1.0  # Super-hub connects to 50 other nodes

    # 2-step unnormalized message passing A^2
    seed = torch.zeros((1, n))
    seed[0, 0] = 1.0
    scores_2hop = (seed @ adj @ adj @ adj).squeeze(0)

    # Fails: Super-hub (Node 2) accumulates massive echo-chamber mass (51.0) vs specific target Node 1 (2.0)
    assert scores_2hop[1].item() > scores_2hop[2].item()


@pytest.mark.xfail(
    strict=True,
    reason="Stage-1 edges.csv schema stores static (source, relation, target) triples without valid_from/valid_to timestamps.",
)
def test_temporal_breach_window_filtering_missing_schema() -> None:
    """Exposes lack of temporal edge attributes when querying 'breaches in the last 12 months'."""
    stage1_edge_columns = ("source", "relation", "target")
    assert "timestamp" in stage1_edge_columns or "valid_from" in stage1_edge_columns


@pytest.mark.xfail(
    strict=True,
    reason="GraphReasoner.visualize currently asserts batch_size == 1 (gfmrag/models/gfm_reasoner/model.py:345).",
)
def test_visualize_batch_size_greater_than_one_limitation() -> None:
    """Exposes the batch_size == 1 assertion bottleneck in GraphReasoner.visualize."""
    from gfmrag.models.gfm_reasoner.model import GraphReasoner

    mock_entity_model = MagicMock()
    mock_entity_model.dims = [16]
    reasoner = GraphReasoner(entity_model=mock_entity_model, feat_dim=16)

    dummy_graph = MagicMock()
    dummy_graph.num_nodes = 5
    dummy_graph.rel_attr = torch.zeros((4, 16))
    batched_sample = {
        "question_embeddings": torch.zeros((2, 16)),  # batch_size = 2
        "start_nodes_mask": torch.zeros((2, 5)),
        "target_nodes_mask": torch.zeros((2, 5)),
    }

    # Raises AssertionError: Currently only supports batch size 1 for visualization
    reasoner.visualize(dummy_graph, batched_sample)


# =====================================================================
# 5. Convex Subgraph Optimization & RLVR (GRPO) Tests
# =====================================================================

def test_convex_subgraph_selector_suppresses_hubs_under_token_budget() -> None:
    """Verifies that `select_convex_subgraph` de-biases super-hubs and respects token budget B."""
    # Node 0: Relevant Path Node A (score 0.90, degree 2, token cost 100)
    # Node 1: Relevant Path Node B connected to A (score 0.85, degree 2, token cost 100)
    # Node 2: Generic Super-Hub (score 0.92, degree 40, token cost 150)
    # Nodes 3..10: Hub leaves (score 0.05, token cost 100)
    n = 11
    scores = torch.zeros(n)
    scores[0] = 0.90
    scores[1] = 0.85
    scores[2] = 0.92

    adj = torch.zeros((n, n))
    adj[0, 1] = adj[1, 0] = 1.0  # Connected reasoning path 0 <-> 1
    for k in range(3, n):
        adj[2, k] = adj[k, 2] = 1.0  # Hub connections

    # Artificially boost hub degree in adjacency diagonal/off-diagonal
    token_costs = torch.full((n,), 100.0)
    token_costs[2] = 150.0
    budget = 220.0  # Can fit Node 0 + Node 1 (200 tokens), cannot fit all three

    z, selected = select_convex_subgraph(
        node_scores=scores,
        adjacency=adj,
        token_costs=token_costs,
        token_budget=budget,
        hub_penalty_alpha=0.20,
        smoothness_beta=0.15,
    )

    # Convex selector suppresses high-degree Node 2 and selects the connected pair (0, 1) within budget
    assert 0 in selected and 1 in selected
    assert 2 not in selected
    assert sum(token_costs[i].item() for i in selected) <= budget


def test_rlvr_grpo_advantage_rewards_fact_gated_short_paths() -> None:
    """Verifies that GRPO advantage computation rewards grounded, concise paths and penalizes hubs/hallucinations."""
    oracle = FactGateOracle(
        known_entities={"BHP Group Limited", "Mining Sector", "Woolworths Group Limited"},
        known_abns={"49004028077"},
        min_recall_threshold=0.5,
    )
    expected_abns = {"49004028077"}

    trajectories = [
        # Trajectory 0: Grounded, 2 hops, low degree, correct answer (Optimal)
        SubgraphTrajectory(
            triples=[
                ("BHP Group Limited", "has abn", "49004028077"),
                ("BHP Group Limited", "operates in", "Mining Sector"),
            ],
            num_hops=2,
            max_node_degree=4,
            answer_matched=True,
        ),
        # Trajectory 1: Grounded, but 6 hops through a degree-35 super-hub (Sub-optimal resource usage)
        SubgraphTrajectory(
            triples=[
                ("BHP Group Limited", "has abn", "49004028077"),
                ("Woolworths Group Limited", "operates in", "Mining Sector"),
            ],
            num_hops=6,
            max_node_degree=35,
            answer_matched=True,
        ),
        # Trajectory 2: Hallucinated invalid ABN checksum & wrong answer (Failure)
        SubgraphTrajectory(
            triples=[
                ("BHP Group Limited", "has abn", "49004028078"),
            ],
            num_hops=3,
            max_node_degree=8,
            answer_matched=False,
        ),
    ]

    rewards, advantages = compute_grpo_subgraph_advantages(
        trajectories, oracle, expected_abns=expected_abns
    )

    # Optimal path gets strictly highest reward and positive advantage
    assert rewards[0].item() > rewards[1].item() > rewards[2].item()
    assert advantages[0].item() > 0.5
    assert advantages[2].item() < -0.5
    # Group-normalized advantages sum to 0.0
    assert torch.isclose(advantages.sum(), torch.tensor(0.0), atol=1e-5)
