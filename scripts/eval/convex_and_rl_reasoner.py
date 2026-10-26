# scripts/eval/convex_and_rl_reasoner.py
"""Convex Optimisation & Reinforcement Learning (RLVR) Pipelines for G-Reasoner.

Addresses structural bottlenecks in Graph Foundation Model retrieval:
1. Multi-Anchor Steiner Bridge Discovery (fixes single-mask OR-pooling dilution).
2. Entropic Optimal Transport / Sinkhorn-Knopp for Cross-Corpus Entity Alignment.
3. Degree-Regularized Convex Subgraph Selection under strict LLM token budgets.
4. Group Relative Policy Optimization (GRPO) verifiable reward & advantage computation
   coupled with the deterministic FactGateOracle.
"""
from __future__ import annotations

import dataclasses
from typing import Dict, List, Optional, Sequence, Set, Tuple

import torch
import torch.nn.functional as F

from scripts.eval.fact_gate import FactGateOracle


def compute_steiner_bridge_scores(
    adjacency: torch.Tensor,
    seed_indices: Sequence[int],
    num_hops: int = 2,
    degree_penalty_exp: float = 0.5,
    eps: float = 1e-6,
) -> torch.Tensor:
    """Compute multi-channel Steiner bridge scores across m distinct seed entities.

    Unlike standard `prepare_input_for_graph_retriever` which collapses all query
    entities into a single `1 x N` binary mask (allowing a node strongly tied to
    just ONE seed to dominate), this propagates `m` separate channels `(m, N)`
    and scores candidate bridge nodes by their degree-regularized geometric mean
    reachability across ALL `m` seeds.

    Args:
        adjacency: Tensor of shape (N, N) representing directed or undirected edges.
        seed_indices: Indices of the m >= 1 anchor entities.
        num_hops: Number of Bellman-Ford / message-passing steps.
        degree_penalty_exp: Exponent alpha for degree normalization d_v^(-alpha).
        eps: Small constant for numerical stability in geometric mean.

    Returns:
        Tensor of shape (N,) with Steiner bridge scores for every node.
    """
    num_nodes = adjacency.size(0)
    m = len(seed_indices)
    if m == 0:
        return torch.zeros(num_nodes, dtype=adjacency.dtype, device=adjacency.device)

    # Symmetrize and add self-loops for reachability propagation
    adj = adjacency.float()
    adj_sym = torch.clamp(adj + adj.t(), max=1.0)
    deg = adj_sym.sum(dim=1).clamp(min=1.0)
    deg_inv = torch.diag(1.0 / deg)
    transition = deg_inv @ adj_sym  # Row-normalized random walk matrix

    # Initialize m separate channels: shape (m, N)
    state = torch.zeros((m, num_nodes), dtype=torch.float32, device=adjacency.device)
    for ch_idx, node_idx in enumerate(seed_indices):
        state[ch_idx, node_idx] = 1.0

    accumulated = state.clone()
    discount = 0.7
    for step in range(1, num_hops + 1):
        state = state @ transition
        accumulated = accumulated + (discount ** step) * state

    # Zero out the seed nodes themselves if we are looking for intermediate bridges
    # (or keep them attenuated); compute geometric mean across all m channels:
    # S(v) = (prod_{i=1}^m accumulated[i, v])^(1/m) * deg(v)^(-degree_penalty_exp)
    log_reach = torch.log(accumulated.clamp(min=eps))
    geom_mean = torch.exp(log_reach.mean(dim=0))

    degree_factor = deg.pow(-degree_penalty_exp)
    scores = geom_mean * degree_factor
    for idx in seed_indices:
        scores[idx] = 0.0  # Exclude trivial seed self-matches when ranking bridges

    return scores


def sinkhorn_entity_alignment(
    cost_matrix: torch.Tensor,
    reg: float = 0.05,
    num_iters: int = 50,
    max_Row_cap: Optional[torch.Tensor] = None,
    max_col_cap: Optional[torch.Tensor] = None,
) -> torch.Tensor:
    """Entropic Optimal Transport (Sinkhorn-Knopp) for Cross-Corpus Entity Linking.

    Prevents greedy many-to-one collapse when aligning unlabelled news mentions
    (Corpus C) to canonical register entities (Corpus A) by enforcing global
    marginal doubly-stochastic constraints:
        min_{P >= 0} <C, P> - reg * H(P)  s.t. P 1 = r, P^T 1 = c

    Args:
        cost_matrix: Shape (N_source, N_target) pairwise distance matrix.
        reg: Entropic regularization parameter epsilon > 0.
        num_iters: Number of Sinkhorn-Knopp alternating Bregman projections.
        max_Row_cap: Optional source marginal distribution r (defaults to uniform).
        max_col_cap: Optional target marginal distribution c (defaults to uniform).

    Returns:
        Transport plan P of shape (N_source, N_target).
    """
    n_src, n_tgt = cost_matrix.shape
    device = cost_matrix.device

    r = max_Row_cap if max_Row_cap is not None else torch.full((n_src,), 1.0 / n_src, device=device)
    c = max_col_cap if max_col_cap is not None else torch.full((n_tgt,), 1.0 / n_tgt, device=device)

    # Gibbs kernel K = exp(-C / reg)
    log_k = -cost_matrix.float() / reg
    log_u = torch.zeros(n_src, device=device)
    log_v = torch.zeros(n_tgt, device=device)
    log_r = torch.log(r.clamp(min=1e-12))
    log_c = torch.log(c.clamp(min=1e-12))

    for _ in range(num_iters):
        log_u = log_r - torch.logsumexp(log_k + log_v.unsqueeze(0), dim=1)
        log_v = log_c - torch.logsumexp(log_k + log_u.unsqueeze(1), dim=0)

    log_p = log_u.unsqueeze(1) + log_k + log_v.unsqueeze(0)
    return torch.exp(log_p)


def select_convex_subgraph(
    node_scores: torch.Tensor,
    adjacency: torch.Tensor,
    token_costs: torch.Tensor,
    token_budget: float,
    hub_penalty_alpha: float = 0.15,
    smoothness_beta: float = 0.10,
    num_steps: int = 80,
    lr: float = 0.05,
) -> Tuple[torch.Tensor, List[int]]:
    """Degree-Regularized Convex Subgraph Optimization under a strict Token Budget.

    Solves the continuous convex relaxation over node selection variables z in [0, 1]^N:
        max_{z in [0, 1]^N}  s^T z - alpha * sum_i d_i z_i^2 - beta * z^T L_G z
        subject to           c^T z <= B

    where:
        - s: G-Reasoner node relevance logits
        - d_i: Node degree in the graph (penalizes generic super-hubs)
        - L_G = D - A: Graph Laplacian (rewards connected reasoning paths)
        - c_i: Token cost of including node i's document/attributes
        - B: Maximum LLM context budget

    Returns:
        Tuple of (optimal continuous weights z, discrete selected node indices within budget).
    """
    n = node_scores.size(0)
    s = node_scores.float().detach()
    adj = adjacency.float().detach()
    adj_sym = torch.clamp(adj + adj.t(), max=1.0)
    deg = adj_sym.sum(dim=1)
    laplacian = torch.diag(deg) - adj_sym
    costs = token_costs.float().detach().clamp(min=1e-3)

    # Initialize z uniformly within budget
    z = torch.clamp(s / (s.max().clamp(min=1.0)), 0.0, 1.0).clone()
    if float(costs @ z) > token_budget:
        z = z * (token_budget / float(costs @ z))

    for _ in range(num_steps):
        # Gradient of objective: s - 2 * alpha * d * z - 2 * beta * L_G z
        grad = s - 2.0 * hub_penalty_alpha * (deg * z) - 2.0 * smoothness_beta * (laplacian @ z)
        z = z + lr * grad

        # Box projection onto [0, 1]^N
        z = torch.clamp(z, 0.0, 1.0)

        # Simplex / Knapsack hyperplane projection: c^T z <= B
        current_cost = float(costs @ z)
        if current_cost > token_budget:
            # Project onto c^T z = B via weighted Euclidean projection
            excess = (current_cost - token_budget) / float(costs @ costs)
            z = torch.clamp(z - excess * costs, 0.0, 1.0)

    # Greedy rounding by utility-to-cost density z_i / c_i within budget B
    ranked_indices = torch.argsort(z, descending=True).tolist()
    selected: List[int] = []
    spent = 0.0
    for idx in ranked_indices:
        if z[idx].item() <= 1e-3:
            continue
        item_cost = float(costs[idx].item())
        if spent + item_cost <= token_budget:
            selected.append(idx)
            spent += item_cost

    return z, selected


@dataclasses.dataclass
class SubgraphTrajectory:
    """Represents a sampled G-Reasoner reasoning trajectory for RLVR training."""
    triples: List[Tuple[str, str, str]]
    num_hops: int
    max_node_degree: int
    answer_matched: bool


def compute_grpo_subgraph_advantages(
    trajectories: Sequence[SubgraphTrajectory],
    oracle: FactGateOracle,
    expected_abns: Optional[Set[str]] = None,
    hop_penalty_weight: float = 0.05,
    hub_penalty_weight: float = 0.02,
    degree_threshold: int = 10,
) -> Tuple[torch.Tensor, torch.Tensor]:
    """Compute Verifiable Rewards and Group Relative Policy Optimization (GRPO) Advantages.

    Scores a group of G sampled reasoning paths from G-Reasoner without human labels:
        R_i = 0.5 * FactGate(tau_i) + 0.5 * AnswerMatch(tau_i)
              - w_hop * max(0, hops_i - 1)
              - w_hub * max(0, max_deg_i - degree_threshold)

    Returns:
        Tuple of (raw_rewards: Tensor[G], grpo_advantages: Tensor[G]).
    """
    rewards: List[float] = []
    for traj in trajectories:
        gate_res = oracle.verify_triples(traj.triples, expected_abns=expected_abns)
        base_reward = 0.5 * gate_res.reward_score + (0.5 if traj.answer_matched else 0.0)
        hop_pen = hop_penalty_weight * max(0, traj.num_hops - 1)
        hub_pen = hub_penalty_weight * max(0, traj.max_node_degree - degree_threshold)
        total_r = max(0.0, base_reward - hop_pen - hub_pen)
        rewards.append(total_r)

    r_tensor = torch.tensor(rewards, dtype=torch.float32)
    if len(rewards) <= 1:
        return r_tensor, torch.zeros_like(r_tensor)

    mean_r = r_tensor.mean()
    std_r = r_tensor.std(unbiased=False)
    if std_r.item() < 1e-6:
        advantages = torch.zeros_like(r_tensor)
    else:
        advantages = (r_tensor - mean_r) / (std_r + 1e-8)

    return r_tensor, advantages
