-- Add image_url and onchain_id to markets table
ALTER TABLE markets ADD COLUMN IF NOT EXISTS image_url TEXT;
ALTER TABLE markets ADD COLUMN IF NOT EXISTS onchain_id INTEGER;
CREATE INDEX IF NOT EXISTS idx_markets_onchain_id ON markets(onchain_id);
