"""End-to-end reproducible demonstration pipeline.

This trains a reference ANFIS classifier/regressor on transparent features and a VAE
anomaly model. It intentionally does not claim to regenerate the thesis' unpublished
weights or its reported 0.970 AUC.
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import torch
from sklearn.metrics import roc_auc_score, precision_recall_fscore_support, accuracy_score
from sklearn.preprocessing import StandardScaler
from data_pipeline import fetch_vnindex, make_features
from crash_label import direct_index_crash_flags
from anfis_hybrid import SugenoANFIS, fit_hybrid
from vae import VAE, vae_loss, reconstruction_error

FEATURES=["log_return","vol_5","vol_20","momentum_5","momentum_20","drawdown_60","rsi_14","macd_hist","stoch_k"]


def main():
    root=Path(__file__).resolve().parents[1]
    df=make_features(fetch_vnindex("max"))
    weekly=df.set_index("date")["close"].resample("W-FRI").last().dropna()
    c=direct_index_crash_flags(weekly)
    # Put weekly crash labels back onto daily observations for a simple demo target.
    c_daily=c["crash"].reindex(pd.date_range(c.index.min(),c.index.max(),freq="D")).ffill().fillna(0)
    df["crash_target"]=df["date"].map(c_daily).fillna(0).astype(float)
    clean=df.dropna(subset=FEATURES).copy()
    X=clean[FEATURES].to_numpy(float); y=clean["crash_target"].to_numpy(float)
    n=len(clean); a=int(n*.80); b=int(n*.90)
    scaler=StandardScaler().fit(X[:a]); Xs=scaler.transform(X)
    model=SugenoANFIS(len(FEATURES),n_rules=8)
    hist=fit_hybrid(model,Xs[:a],y[:a],epochs=80,lr=.01)
    with torch.no_grad(): score=model(torch.tensor(Xs,dtype=torch.float32)).numpy()
    prob=1/(1+np.exp(-score))
    # VAE trained on non-crash training observations, as a normal-behaviour model.
    vae=VAE(len(FEATURES)); opt=torch.optim.Adam(vae.parameters(),lr=1e-3)
    xnormal=torch.tensor(Xs[:a][y[:a]==0],dtype=torch.float32)
    for _ in range(60):
        vae.train(); opt.zero_grad(); recon,mu,lv=vae(xnormal); loss,_=vae_loss(xnormal,recon,mu,lv); loss.backward(); opt.step()
    err=reconstruction_error(vae,torch.tensor(Xs,dtype=torch.float32)).numpy()
    def metrics(lo,hi):
        yt=y[lo:hi]; ps=prob[lo:hi]; yp=(ps>=.5).astype(int)
        p,r,f,_=precision_recall_fscore_support(yt,yp,average="binary",zero_division=0)
        auc=roc_auc_score(yt,ps) if len(np.unique(yt))>1 else None
        return {"n":int(hi-lo),"accuracy":accuracy_score(yt,yp),"precision":p,"recall":r,"f1":f,"auc":auc}
    out={"disclosure":"Reference implementation; not the original thesis-trained model.","train":metrics(0,a),"validation":metrics(a,b),"test":metrics(b,n),"final_hybrid_loss":hist[-1],"latest_date":str(clean.iloc[-1]["date"].date()),"latest_anfis_probability":float(prob[-1]),"latest_vae_reconstruction_error":float(err[-1])}
    (root/"data"/"demo-model-output.json").write_text(json.dumps(out,indent=2),encoding="utf-8")
    print(json.dumps(out,indent=2))

if __name__=="__main__": main()
