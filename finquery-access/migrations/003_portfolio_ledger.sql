-- FinQuery Portfolio Intelligence v1.1: additive, server-owned append-only trading journal.
-- All values in VND/share; identity from verified server cookie. Never store credentials.
-- No DELETE/UPDATE endpoint. Each event is idempotent and serialized per account.
CREATE TABLE IF NOT EXISTS public.finquery_portfolio_transactions (
  event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES public.finquery_users(id) ON DELETE CASCADE,
  request_key VARCHAR(100) NOT NULL,
  kind VARCHAR(12) NOT NULL CHECK (kind IN ('DEPOSIT','WITHDRAW','BUY','SELL','DIVIDEND')),
  symbol VARCHAR(12),
  quantity BIGINT,
  unit_price_vnd NUMERIC(24,4),
  fee_vnd NUMERIC(24,4) NOT NULL DEFAULT 0 CHECK(fee_vnd >= 0),
  amount_vnd NUMERIC(24,4),
  trade_date DATE NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(user_id,request_key),
  CHECK (
    ((kind IN ('BUY','SELL')) AND symbol ~ '^[A-Z0-9]{2,12}$' AND quantity BETWEEN 1 AND 1000000000 AND unit_price_vnd > 0 AND unit_price_vnd <= 1000000000 AND amount_vnd IS NULL)
    OR ((kind IN ('DEPOSIT','WITHDRAW')) AND symbol IS NULL AND quantity IS NULL AND unit_price_vnd IS NULL AND amount_vnd > 0 AND amount_vnd <= 1000000000000)
    OR (kind='DIVIDEND' AND symbol ~ '^[A-Z0-9]{2,12}$' AND quantity IS NULL AND unit_price_vnd IS NULL AND amount_vnd > 0 AND amount_vnd <= 1000000000000)
  )
);
CREATE INDEX IF NOT EXISTS finquery_portfolio_events_user_idx ON public.finquery_portfolio_transactions(user_id,event_id);
CREATE OR REPLACE FUNCTION public.finquery_append_portfolio_event(
  p_user UUID,p_key VARCHAR,p_kind VARCHAR,p_symbol VARCHAR,p_quantity BIGINT,
  p_price NUMERIC,p_fee NUMERIC,p_amount NUMERIC,p_date DATE
) RETURNS TABLE(event_id BIGINT,duplicate BOOLEAN)
LANGUAGE plpgsql SECURITY INVOKER SET search_path = public, pg_temp AS $fn$
DECLARE
  v_id BIGINT; v_cash NUMERIC(30,4); v_shares NUMERIC(30,4); v_last_date DATE;
  v_row public.finquery_portfolio_transactions%ROWTYPE;
BEGIN
  IF p_user IS NULL OR p_key !~ '^[A-Za-z0-9:_-]{16,100}$' OR p_date IS NULL
    OR p_date > CURRENT_DATE+1 OR p_date < DATE '1990-01-01'
    OR p_kind NOT IN ('DEPOSIT','WITHDRAW','BUY','SELL','DIVIDEND')
    OR COALESCE(p_fee,-1) < 0 THEN
    RAISE EXCEPTION 'FINQUERY_INVALID_EVENT';
  END IF;
  IF p_kind IN ('BUY','SELL') THEN
    IF p_symbol IS NULL OR p_symbol !~ '^[A-Z0-9]{2,12}$'
       OR p_quantity NOT BETWEEN 1 AND 1000000000 OR p_price IS NULL
       OR p_price <= 0 OR p_price > 1000000000 OR p_amount IS NOT NULL THEN
      RAISE EXCEPTION 'FINQUERY_INVALID_TRADE';
    END IF;
  ELSIF p_kind IN ('DEPOSIT','WITHDRAW') THEN
    IF p_symbol IS NOT NULL OR p_quantity IS NOT NULL OR p_price IS NOT NULL
      OR p_amount IS NULL OR p_amount <= 0 OR p_amount > 1000000000000 OR p_fee <> 0 THEN
      RAISE EXCEPTION 'FINQUERY_INVALID_CASHFLOW';
    END IF;
  ELSE
    IF p_symbol IS NULL OR p_symbol !~ '^[A-Z0-9]{2,12}$' OR
       p_quantity IS NOT NULL OR p_price IS NOT NULL OR
       p_amount IS NULL OR p_amount <= 0 OR p_amount > 1000000000000 OR p_fee <> 0 THEN
      RAISE EXCEPTION 'FINQUERY_INVALID_DIVIDEND';
    END IF;
  END IF;
  PERFORM pg_advisory_xact_lock(hashtextextended('finquery-portfolio:'||p_user::text,0));
  SELECT * INTO v_row FROM public.finquery_portfolio_transactions AS e
    WHERE e.user_id=p_user AND e.request_key=p_key LIMIT 1;
  IF FOUND THEN
    IF v_row.kind IS DISTINCT FROM p_kind OR v_row.symbol IS DISTINCT FROM p_symbol
      OR v_row.quantity IS DISTINCT FROM p_quantity OR v_row.unit_price_vnd IS DISTINCT FROM p_price
      OR v_row.fee_vnd IS DISTINCT FROM p_fee OR v_row.amount_vnd IS DISTINCT FROM p_amount
      OR v_row.trade_date IS DISTINCT FROM p_date THEN
      RAISE EXCEPTION 'FINQUERY_IDEMPOTENCY_CONFLICT';
    END IF;
    RETURN QUERY SELECT v_row.event_id,TRUE;
    RETURN;
  END IF;
  SELECT max(e.trade_date) INTO v_last_date FROM public.finquery_portfolio_transactions e WHERE e.user_id=p_user;
  IF v_last_date IS NOT NULL AND p_date < v_last_date THEN
    RAISE EXCEPTION 'FINQUERY_TRADE_DATE_OUT_OF_ORDER';
  END IF;
  SELECT COALESCE(SUM(
    CASE e.kind WHEN 'DEPOSIT' THEN e.amount_vnd WHEN 'WITHDRAW' THEN -e.amount_vnd
      WHEN 'DIVIDEND' THEN e.amount_vnd WHEN 'BUY' THEN -(e.quantity*e.unit_price_vnd+e.fee_vnd)
      WHEN 'SELL' THEN e.quantity*e.unit_price_vnd-e.fee_vnd ELSE 0 END),0)
    INTO v_cash FROM public.finquery_portfolio_transactions e WHERE e.user_id=p_user;
  IF p_kind='BUY' AND v_cash < p_quantity*p_price+p_fee THEN
    RAISE EXCEPTION 'FINQUERY_INSUFFICIENT_CASH';
  END IF;
  IF p_kind='WITHDRAW' AND v_cash < p_amount THEN
    RAISE EXCEPTION 'FINQUERY_INSUFFICIENT_CASH';
  END IF;
  IF p_kind='SELL' THEN
    SELECT COALESCE(SUM(CASE e.kind WHEN 'BUY' THEN e.quantity WHEN 'SELL' THEN -e.quantity ELSE 0 END),0)
    INTO v_shares FROM public.finquery_portfolio_transactions e WHERE e.user_id=p_user AND e.symbol=p_symbol;
    IF v_shares < p_quantity THEN RAISE EXCEPTION 'FINQUERY_INSUFFICIENT_SHARES'; END IF;
  END IF;
  INSERT INTO public.finquery_portfolio_transactions
    (user_id,request_key,kind,symbol,quantity,unit_price_vnd,fee_vnd,amount_vnd,trade_date)
  VALUES(p_user,p_key,p_kind,p_symbol,p_quantity,p_price,p_fee,p_amount,p_date)
  RETURNING public.finquery_portfolio_transactions.event_id INTO v_id;
  RETURN QUERY SELECT v_id,FALSE;
END $fn$;
