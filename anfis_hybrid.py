"""Compact first-order Sugeno ANFIS reference implementation.

The supplied thesis explains ANFIS layers and states hybrid learning using gradient
learning + least-squares estimation, but does not provide the original MATLAB project,
full rule base, membership counts, or trained parameters. This implementation therefore
reproduces the *method class*, not the unpublished trained object.
"""
from __future__ import annotations
import numpy as np
import torch
from torch import nn


class SugenoANFIS(nn.Module):
    def __init__(self, n_features: int, n_rules: int = 8):
        super().__init__()
        self.n_features = n_features
        self.n_rules = n_rules
        self.centers = nn.Parameter(torch.linspace(-1.2, 1.2, n_rules).unsqueeze(1).repeat(1, n_features))
        self.log_sigmas = nn.Parameter(torch.zeros(n_rules, n_features))
        # Consequent: b + sum_j p_j x_j for each rule. Updated by least squares.
        self.register_buffer("consequents", torch.zeros(n_rules, n_features + 1))

    def firing(self, x: torch.Tensor) -> torch.Tensor:
        sig = torch.exp(self.log_sigmas).clamp_min(1e-3)
        # Gaussian membership, then product t-norm in log-space for stability.
        log_mu = -0.5 * ((x[:, None, :] - self.centers[None, :, :]) / sig[None, :, :]) ** 2
        log_w = log_mu.sum(dim=2)
        w = torch.softmax(log_w, dim=1)
        return w

    def design_matrix(self, x: torch.Tensor, w: torch.Tensor) -> torch.Tensor:
        ones = torch.ones((x.shape[0], 1), dtype=x.dtype, device=x.device)
        xb = torch.cat([ones, x], dim=1)  # N x (D+1)
        return (w[:, :, None] * xb[:, None, :]).reshape(x.shape[0], -1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        w = self.firing(x)
        xb = torch.cat([torch.ones((x.shape[0],1),device=x.device,dtype=x.dtype), x], dim=1)
        rule_y = torch.einsum("nd,rd->nr", xb, self.consequents)
        return (w * rule_y).sum(dim=1)

    @torch.no_grad()
    def fit_consequents(self, x: torch.Tensor, y: torch.Tensor, ridge: float = 1e-4):
        w = self.firing(x)
        A = self.design_matrix(x, w)
        eye = torch.eye(A.shape[1], dtype=A.dtype, device=A.device)
        theta = torch.linalg.solve(A.T @ A + ridge * eye, A.T @ y)
        self.consequents.copy_(theta.reshape(self.n_rules, self.n_features + 1))


def fit_hybrid(model: SugenoANFIS, x: np.ndarray, y: np.ndarray, epochs: int = 100,
               lr: float = 1e-2, ridge: float = 1e-4, seed: int = 42):
    """Alternates least-squares consequent fitting and gradient premise updates."""
    torch.manual_seed(seed)
    xt = torch.as_tensor(x, dtype=torch.float32)
    yt = torch.as_tensor(y, dtype=torch.float32)
    opt = torch.optim.Adam([model.centers, model.log_sigmas], lr=lr)
    history=[]
    for _ in range(epochs):
        model.fit_consequents(xt, yt, ridge=ridge)
        opt.zero_grad()
        pred=model(xt)
        loss=torch.mean((pred-yt)**2)
        loss.backward()
        opt.step()
        history.append(float(loss.detach()))
    model.fit_consequents(xt, yt, ridge=ridge)
    return history
