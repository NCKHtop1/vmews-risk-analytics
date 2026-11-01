-- FinQuery Portfolio policies v1: configuration only, no stored trade instructions.
-- API authentication supplies user_id; revisional writes prevent overwrites across devices.
CREATE TABLE IF NOT EXISTS public.finquery_portfolio_policies (
  user_id UUID PRIMARY KEY REFERENCES public.finquery_users(id) ON DELETE CASCADE,
  preset VARCHAR(24) NOT NULL CHECK (preset IN ('balanced','equal','defensive','focused')),
  cash_pct SMALLINT NOT NULL CHECK(cash_pct BETWEEN 0 AND 50),
  drift_pct SMALLINT NOT NULL CHECK(drift_pct BETWEEN 2 AND 15),
  revision BIGINT NOT NULL DEFAULT 1 CHECK(revision >= 1),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
