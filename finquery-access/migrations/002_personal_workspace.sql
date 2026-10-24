-- Additive user-scoped workspace. Google identity still comes exclusively from the auth session.
-- This table stores configuration only: do not place API tokens, passwords or trading credentials here.
CREATE TABLE IF NOT EXISTS public.finquery_user_workspaces (
  user_id uuid PRIMARY KEY REFERENCES public.finquery_users(id) ON DELETE CASCADE,
  watchlist jsonb NOT NULL DEFAULT '[]'::jsonb,
  strategies jsonb NOT NULL DEFAULT '[]'::jsonb,
  settings jsonb NOT NULL DEFAULT '{}'::jsonb,
  revision bigint NOT NULL DEFAULT 1 CHECK (revision >= 1),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT workspace_watchlist_array CHECK (jsonb_typeof(watchlist) = 'array'),
  CONSTRAINT workspace_strategies_array CHECK (jsonb_typeof(strategies) = 'array'),
  CONSTRAINT workspace_settings_object CHECK (jsonb_typeof(settings) = 'object')
);
COMMENT ON TABLE public.finquery_user_workspaces IS
  'Per-session-user FinQuery watchlists and screener presets; no secrets; optimistic revision control';
