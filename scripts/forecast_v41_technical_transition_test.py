from __future__ import annotations

import math

import numpy as np
import pandas as pd

import forecast_v41_runtime_patch as runtime_patch
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


def test_large_move_threshold_is_calibration_only_and_requires_depth():
    calibration=pd.DataFrame({'target3':np.linspace(-.05,.05,200)})
    threshold=runtime_patch._large_move_threshold(calibration,'target3')
    expected=float(np.quantile(np.abs(calibration['target3'].to_numpy(dtype=float)),.90))
    assert math.isclose(threshold,expected,rel_tol=0,abs_tol=1e-15)

    # Arbitrary holdout values are deliberately not an input to the threshold helper.
    absurd_holdout=np.array([1e6,-1e6,0.0])
    assert absurd_holdout.max()>threshold
    assert math.isclose(runtime_patch._large_move_threshold(calibration,'target3'),threshold,rel_tol=0,abs_tol=0)

    try:
        runtime_patch._large_move_threshold(calibration.iloc[:99],'target3')
    except RuntimeError:
        pass
    else:
        raise AssertionError('large-move calibration must fail closed below 100 rows')


def _controlled_transition_audit():
    dates=pd.bdate_range('2026-01-02',periods=110)
    calibration=pd.DataFrame({
        'date':dates[:100],
        'symbol':['CAL']*100,
        'target3':np.linspace(.001,.05,100),
        'maturity3':dates[:100],
        '_bull_eligible':np.ones(100,dtype=int),
        '_bull_transition':(np.arange(100)%5==0).astype(int),
        '_prob':np.linspace(.10,.90,100),
    })
    train=calibration.iloc[:5].copy()
    holdout_dates=dates[100:106]
    holdout=pd.DataFrame({
        'date':holdout_dates,
        'symbol':['H']*6,
        'target3':[.10,.02,.08,.07,-.01,.01],
        'maturity3':[holdout_dates[0],holdout_dates[1],holdout_dates[2],holdout_dates[3],holdout_dates[4],dates[-1]+pd.Timedelta(days=30)],
        '_bull_eligible':np.ones(6,dtype=int),
        '_bull_transition':[1,0,1,1,0,0],
        '_prob':[.90,.86,.84,.40,.20,.50],
    })
    enriched=pd.concat([train,calibration,holdout],ignore_index=True)

    class FakeModel:
        def __init__(self):
            self.fit_rows=None
        def fit(self,x,y):
            self.fit_rows=len(y)
            return self
        def predict_proba(self,x):
            p=np.asarray(x,dtype=float).reshape(-1)
            return np.column_stack([1.0-p,p])

    models=[]
    original_split=runtime_patch.v41._chronological_split
    original_classifier=runtime_patch.v41._classifier
    original_matrix=runtime_patch.v41._matrix
    try:
        runtime_patch.v41._chronological_split=lambda rows:(train,calibration,holdout)
        def make_model(seed):
            model=FakeModel(); models.append(model); return model
        runtime_patch.v41._classifier=make_model
        runtime_patch.v41._matrix=lambda rows:rows[['_prob']].to_numpy(dtype=float)
        audit,_,threshold=runtime_patch._evaluate_side_hardened(enriched,side='bull')
    finally:
        runtime_patch.v41._chronological_split=original_split
        runtime_patch.v41._classifier=original_classifier
        runtime_patch.v41._matrix=original_matrix
    return audit,threshold,models,enriched


def test_transition_recall_fpr_and_large_move_arithmetic():
    audit,threshold,models,enriched=_controlled_transition_audit()
    # q90 calibration probability is below .84, selecting first three holdout rows.
    assert threshold<.84
    assert audit['selectedRows']==3
    assert audit['positiveRows']==3
    assert audit['negativeRows']==3
    assert audit['truePositiveRows']==2
    assert audit['falsePositiveRows']==1
    assert math.isclose(audit['precision'],2/3,rel_tol=0,abs_tol=1e-12)
    assert math.isclose(audit['transitionRecall'],2/3,rel_tol=0,abs_tol=1e-12)
    assert math.isclose(audit['falsePositiveRate'],1/3,rel_tol=0,abs_tol=1e-12)

    large_threshold=audit['largeMoveThresholdAbsT3']
    assert audit['largeMoveThresholdSource']=='CALIBRATION_ONLY_ABS_T3_Q90'
    assert audit['largeMoveDefinitionFrozenBeforeHoldout'] is True
    assert large_threshold==runtime_patch._large_move_threshold(
        pd.DataFrame({'target3':np.linspace(.001,.05,100)}),'target3'
    )
    assert audit['largeMoveRows']==3
    assert audit['capturedLargeMoveRows']==2
    assert math.isclose(audit['largeMoveCaptureRate'],2/3,rel_tol=0,abs_tol=1e-12)
    assert math.isclose(audit['selectedLargeMoveShare'],2/3,rel_tol=0,abs_tol=1e-12)

    for field in ('brierSkill','precision','transitionRecall','falsePositiveRate','meanSignedT3Return','positiveSignedReturnShare','largeMoveCaptureRate','selectedLargeMoveShare'):
        assert math.isfinite(float(audit[field])),field

    # The second fit is the production refit and must exclude the future-maturity row.
    matured_expected=int((enriched['maturity3']<=enriched['date'].max()).sum())
    assert len(models)==2
    assert models[1].fit_rows==matured_expected
    assert audit['productionRefitRows']==matured_expected
    assert audit['productionRefitUsesOnlyMaturedLabels'] is True


def test_holdout_changes_cannot_redefine_large_move_threshold():
    audit_a,_,_,_=_controlled_transition_audit()
    threshold_a=audit_a['largeMoveThresholdAbsT3']
    calibration=pd.DataFrame({'target3':np.linspace(.001,.05,100)})
    # A radically different hypothetical holdout leaves the calibration-frozen threshold unchanged.
    hypothetical_holdout=np.array([1000.0,-1000.0,500.0])
    assert hypothetical_holdout.max()>threshold_a
    threshold_b=runtime_patch._large_move_threshold(calibration,'target3')
    assert math.isclose(threshold_a,threshold_b,rel_tol=0,abs_tol=1e-15)


if __name__=='__main__':
    tests=[
        test_point_in_time_features_are_future_invariant,
        test_labels_use_future_but_features_do_not,
        test_cross_geometry_has_expected_sign,
        test_eligibility_requires_convergence_toward_cross,
        test_large_move_threshold_is_calibration_only_and_requires_depth,
        test_transition_recall_fpr_and_large_move_arithmetic,
        test_holdout_changes_cannot_redefine_large_move_threshold,
    ]
    for test in tests:
        test(); print(f'{test.__name__}: PASS')
