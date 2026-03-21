-- ═══════════════════════════════════════════════════
-- CRYPTOPREDICT — DATABASE SCHEMA
-- Run this in Supabase SQL Editor
-- ═══════════════════════════════════════════════════

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ── USERS ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    telegram_id     BIGINT UNIQUE,
    username        TEXT,
    display_name    TEXT,
    wallet_address  TEXT,
    usdc_balance    NUMERIC(18,6) DEFAULT 0,
    cpred_balance   NUMERIC(18,6) DEFAULT 0,
    cpred_staked    NUMERIC(18,6) DEFAULT 0,
    total_pnl       NUMERIC(18,6) DEFAULT 0,
    win_count       INTEGER DEFAULT 0,
    loss_count      INTEGER DEFAULT 0,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ── MARKETS ────────────────────────────────────────
CREATE TYPE market_status AS ENUM ('open', 'closed', 'resolving', 'resolved', 'cancelled');
CREATE TYPE market_category AS ENUM ('crypto', 'macro', 'defi', 'nft', 'governance', 'other');

CREATE TABLE IF NOT EXISTS markets (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    creator_id      UUID REFERENCES users(id),
    title           TEXT NOT NULL,
    description     TEXT,
    category        market_category DEFAULT 'crypto',
    asset_symbol    TEXT,              -- es. 'BTC', 'ETH', 'SOL'
    resolution_type TEXT DEFAULT 'price_target', -- 'price_target' | 'manual' | 'oracle'
    resolution_rule TEXT,              -- es. "BTC price > 100000 at expiry"
    target_price    NUMERIC(18,6),     -- per mercati price_target
    target_direction TEXT,             -- 'above' | 'below'
    pool_size       NUMERIC(18,6) DEFAULT 0,
    yes_stake       NUMERIC(18,6) DEFAULT 0,
    no_stake        NUMERIC(18,6) DEFAULT 0,
    yes_pct         NUMERIC(5,2) DEFAULT 50,
    no_pct          NUMERIC(5,2) DEFAULT 50,
    participant_count INTEGER DEFAULT 0,
    status          market_status DEFAULT 'open',
    outcome         BOOLEAN,           -- TRUE=YES, FALSE=NO, NULL=pending
    starts_at       TIMESTAMPTZ DEFAULT NOW(),
    expires_at      TIMESTAMPTZ NOT NULL,
    resolved_at     TIMESTAMPTZ,
    -- Yield tracking
    yield_accrued   NUMERIC(18,6) DEFAULT 0,
    yield_per_day   NUMERIC(18,6) DEFAULT 0,
    -- Fees
    creator_fee_earned NUMERIC(18,6) DEFAULT 0,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ── POSITIONS ──────────────────────────────────────
CREATE TYPE position_status AS ENUM ('open', 'sold', 'won', 'lost', 'refunded');

CREATE TABLE IF NOT EXISTS positions (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL REFERENCES users(id),
    market_id       UUID NOT NULL REFERENCES markets(id),
    side            BOOLEAN NOT NULL,  -- TRUE=YES, FALSE=NO
    stake           NUMERIC(18,6) NOT NULL,
    shares          NUMERIC(18,6) NOT NULL,  -- quota del pool al momento dell'acquisto
    entry_pct       NUMERIC(5,2),      -- probabilità al momento dell'acquisto
    potential_payout NUMERIC(18,6),
    actual_payout   NUMERIC(18,6),
    yield_share     NUMERIC(18,6) DEFAULT 0, -- yield accumulato per questa posizione
    status          position_status DEFAULT 'open',
    opened_at       TIMESTAMPTZ DEFAULT NOW(),
    closed_at       TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ── TRANSACTIONS ───────────────────────────────────
CREATE TYPE tx_type AS ENUM (
    'deposit', 'withdraw',
    'bet_place', 'bet_win', 'bet_loss', 'bet_refund',
    'position_sell',
    'yield_credit',
    'staking_reward',
    'presale_purchase',
    'fee_deducted'
);

CREATE TABLE IF NOT EXISTS transactions (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL REFERENCES users(id),
    type            tx_type NOT NULL,
    amount          NUMERIC(18,6) NOT NULL,
    currency        TEXT DEFAULT 'USDC',
    market_id       UUID REFERENCES markets(id),
    position_id     UUID REFERENCES positions(id),
    description     TEXT,
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ── YIELD SNAPSHOTS ────────────────────────────────
-- Snapshot giornaliero del yield per ogni mercato
CREATE TABLE IF NOT EXISTS yield_snapshots (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    market_id       UUID NOT NULL REFERENCES markets(id),
    pool_size       NUMERIC(18,6),
    yield_generated NUMERIC(18,6),
    winner_share    NUMERIC(18,6),
    staker_share    NUMERIC(18,6),
    treasury_share  NUMERIC(18,6),
    apy_applied     NUMERIC(8,6),
    snapshot_date   DATE DEFAULT CURRENT_DATE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ── STAKING ────────────────────────────────────────
CREATE TYPE stake_pool AS ENUM ('flexible', '30d', '90d');

CREATE TABLE IF NOT EXISTS staking_positions (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL REFERENCES users(id),
    pool            stake_pool DEFAULT 'flexible',
    amount          NUMERIC(18,6) NOT NULL,
    apy             NUMERIC(6,4) NOT NULL,
    rewards_earned  NUMERIC(18,6) DEFAULT 0,
    locked_until    TIMESTAMPTZ,
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ── PRESALE ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS presale_purchases (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID REFERENCES users(id),
    email           TEXT,
    telegram_id     BIGINT,
    stage           INTEGER DEFAULT 1,
    amount_usdc     NUMERIC(18,6) NOT NULL,
    cpred_amount    NUMERIC(18,6) NOT NULL,
    price_per_cpred NUMERIC(18,6) NOT NULL,
    payment_method  TEXT DEFAULT 'USDC',
    payment_status  TEXT DEFAULT 'pending', -- pending | confirmed | failed
    nowpayments_id  TEXT,
    wallet_address  TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    confirmed_at    TIMESTAMPTZ
);

-- ── MARKET SECONDARY (Vendi Quote) ─────────────────
CREATE TABLE IF NOT EXISTS secondary_listings (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    position_id     UUID NOT NULL REFERENCES positions(id),
    seller_id       UUID NOT NULL REFERENCES users(id),
    buyer_id        UUID REFERENCES users(id),
    ask_price       NUMERIC(18,6) NOT NULL,
    shares_pct      NUMERIC(5,2) DEFAULT 100, -- % delle quote messe in vendita
    status          TEXT DEFAULT 'open',       -- open | sold | cancelled
    listed_at       TIMESTAMPTZ DEFAULT NOW(),
    sold_at         TIMESTAMPTZ
);

-- ── INDEXES ────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_markets_status       ON markets(status);
CREATE INDEX IF NOT EXISTS idx_markets_expires_at   ON markets(expires_at);
CREATE INDEX IF NOT EXISTS idx_markets_category     ON markets(category);
CREATE INDEX IF NOT EXISTS idx_positions_user       ON positions(user_id);
CREATE INDEX IF NOT EXISTS idx_positions_market     ON positions(market_id);
CREATE INDEX IF NOT EXISTS idx_positions_status     ON positions(status);
CREATE INDEX IF NOT EXISTS idx_transactions_user    ON transactions(user_id);
CREATE INDEX IF NOT EXISTS idx_transactions_type    ON transactions(type);
CREATE INDEX IF NOT EXISTS idx_yield_market_date    ON yield_snapshots(market_id, snapshot_date);

-- ── ROW LEVEL SECURITY ─────────────────────────────
ALTER TABLE users              ENABLE ROW LEVEL SECURITY;
ALTER TABLE markets            ENABLE ROW LEVEL SECURITY;
ALTER TABLE positions          ENABLE ROW LEVEL SECURITY;
ALTER TABLE transactions       ENABLE ROW LEVEL SECURITY;
ALTER TABLE staking_positions  ENABLE ROW LEVEL SECURITY;
ALTER TABLE presale_purchases  ENABLE ROW LEVEL SECURITY;

-- Policy: service_role bypassa tutto (il backend usa service_role key)
-- Il frontend NON chiama Supabase direttamente — tutto passa per le API FastAPI

-- ── UPDATED_AT TRIGGER ─────────────────────────────
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$ language 'plpgsql';

CREATE TRIGGER trig_users_updated_at
    BEFORE UPDATE ON users FOR EACH ROW EXECUTE PROCEDURE update_updated_at();
CREATE TRIGGER trig_markets_updated_at
    BEFORE UPDATE ON markets FOR EACH ROW EXECUTE PROCEDURE update_updated_at();
CREATE TRIGGER trig_staking_updated_at
    BEFORE UPDATE ON staking_positions FOR EACH ROW EXECUTE PROCEDURE update_updated_at();
