"""Small VAE for market-feature anomaly detection."""
from __future__ import annotations
import torch
from torch import nn

class VAE(nn.Module):
    def __init__(self, n_features: int, hidden: int = 32, latent: int = 6):
        super().__init__()
        self.enc = nn.Sequential(nn.Linear(n_features, hidden), nn.ReLU(), nn.Linear(hidden, hidden//2), nn.ReLU())
        self.mu = nn.Linear(hidden//2, latent)
        self.logvar = nn.Linear(hidden//2, latent)
        self.dec = nn.Sequential(nn.Linear(latent, hidden//2), nn.ReLU(), nn.Linear(hidden//2, hidden), nn.ReLU(), nn.Linear(hidden, n_features))
    def encode(self,x):
        h=self.enc(x); return self.mu(h),self.logvar(h)
    def reparam(self,mu,logvar):
        std=torch.exp(.5*logvar); return mu+torch.randn_like(std)*std
    def forward(self,x):
        mu,lv=self.encode(x); z=self.reparam(mu,lv); return self.dec(z),mu,lv

def vae_loss(x,recon,mu,logvar,beta=1e-3):
    recon_loss=torch.mean((x-recon)**2,dim=1)
    kl=-.5*torch.mean(1+logvar-mu.pow(2)-logvar.exp(),dim=1)
    return (recon_loss+beta*kl).mean(),recon_loss.detach()

@torch.no_grad()
def reconstruction_error(model,x):
    model.eval(); recon,_,_=model(x); return torch.mean((x-recon)**2,dim=1)
