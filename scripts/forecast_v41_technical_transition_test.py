from __future__ import annotations

import numpy as np
import pandas as pd

from forecast_v41_technical_transition import (
    RADAR_FEATURE_COLUMNS,
    TECHNICAL_FEATURE_COLUMNS,
    add_transition_features,
    add_transition_labels,
)


def synthetic_panel(symbols=8, sessions=420):
    dates = pd.bdate_range('2025-01-02', periods=sessions)
    frames=[]
    for si in range(symbols):
        t=np.arange(sessions,dtype=float)
        # Smooth cyclical momentum with symbol phase shifts creates repeated crossings.
        ret=.0005 + .008*np.sin((t+si*4)/15.0) + .002*np.cos((t+si)/5.0)
        close=30000*np.exp(np.cumsum(ret))*(1+si*.02)
        macd=.003*np.sin((t+si*5)/12.0)
        trend10=.02*np.sin((t+si*4)/17.0)
        trend20=.015*np.sin((t+si*4-2)/20.0)
        trend50=.01*np.sin((t+si)/30.0)
        volume=1_000_000*(1+.25*np.sin((t+si)/7.0))
        f=pd.DataFrame({
            'date':dates,'symbol':f'S{si:02d}','close':close,'volume':volume,
            'macd_norm':macd,'trend10':trend10,'trend20':trend20,'trend50':trend50,
            'rsi14':np.clip(.5+.18*np.sin((t+si)/13.0),.05,.95),
            'vol20':.014+.003*np.sin((t+si)/25.0),
            'volume_ratio20':1+.2*np.sin((t+si)/7.0),
            'volume_z20':.8*np.sin((t+si)/7.0),
            'ret5':pd.Series(np.log(close)).diff(5).to_numpy(),
            'ret20':pd.Series(np.log(close)).diff(20).to_numpy(),
            'atr14':.018,'relative_ret5':0.0,'relative_ret20':0.0,
            'sector_relative5':0.0,'breadth5':.55,'market_ret5':.002,
        })
        logc=np.log(close)
        f['target3']=pd.Series(logc).shift(-3)-pd.Series(logc)
        f['maturity3']=pd.Series(dates).shift(-3)
        frames.append(f)
    panel=pd.concat(frames,ignore_index=True).sort_values(['date','symbol']).reset_index(drop=True)
    return panel


def test_point_in_time_features_are_future_invariant():
    panel=synthetic_panel(symbols=2,sessions=120)
    cutoff=panel['date'].sort_values().unique()[-6]
    original=add_transition_features(panel.loc[panel['date']<=cutoff].copy())
    # Append deliberately absurd future observations; prior features must not move.
    future=panel.loc[panel['date']>cutoff].copy()
    future['macd_norm']=99
    future['close']=1e9
    extended=add_transition_features(pd.concat([panel.loc[panel['date']<=cutoff],future],ignore_index=True))
    left=original.loc[original['date']<=cutoff, ['symbol','date',*TECHNICAL_FEATURE_COLUMNS]].reset_index(drop=True)
    right=extended.loc[extended['date']<=cutoff, ['symbol','date',*TECHNICAL_FEATURE_COLUMNS]].reset_index(drop=True)
    pd.testing.assert_frame_equal(left,right,check_dtype=False,check_exact=False,rtol=1e-12,atol=1e-12)


def test_labels_use_future_but_features_do_not():
    panel=add_transition_features(synthetic_panel())
    labelled=add_transition_labels(panel)
    assert labelled['_bull_transition'].sum()>0
    assert labelled['_bear_transition'].sum()>0
    assert not any(name.startswith('_') for name in RADAR_FEATURE_COLUMNS)
    assert '_bull_transition' not in RADAR_FEATURE_COLUMNS
    assert '_bear_transition' not in RADAR_FEATURE_COLUMNS


def test_cross_geometry_has_expected_sign():
    panel=add_transition_features(synthetic_panel(symbols=1,sessions=160)).sort_values('date')
    approaching=panel[(panel['macd_hist_norm']<0)&(panel['macd_hist_delta1']>0)].dropna()
    assert len(approaching)>0
    assert (approaching['macd_cross_velocity']>0).mean()>.95


def test_eligibility_requires_convergence_toward_cross():
    panel=add_transition_features(synthetic_panel(symbols=2,sessions=180))
    labelled=add_transition_labels(panel)
    bull=labelled.loc[labelled['_bull_eligible'].eq(1)]
    bear=labelled.loc[labelled['_bear_eligible'].eq(1)]
    assert len(bull)>0 and len(bear)>0
    assert (((bull['macd_hist_norm']<=0)&(bull['macd_hist_delta1']>0)) | ((bull['trend10_20_gap']<=0)&(bull['trend10_20_delta1']>0))).all()
    assert (((bear['macd_hist_norm']>=0)&(bear['macd_hist_delta1']<0)) | ((bear['trend10_20_gap']>=0)&(bear['trend10_20_delta1']<0))).all()


if __name__=='__main__':
    tests=[
        test_point_in_time_features_are_future_invariant,
        test_labels_use_future_but_features_do_not,
        test_cross_geometry_has_expected_sign,
        test_eligibility_requires_convergence_toward_cross,
    ]
    for test in tests:
        test(); print(f'{test.__name__}: PASS')
