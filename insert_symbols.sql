-- Insert stock symbols
INSERT INTO symbols (id, ticker, name, exchange, asset_type, is_active, metadata_json, created_at, updated_at) VALUES
-- Your existing positions
(gen_random_uuid(), 'AMD', 'Advanced Micro Devices', 'NASDAQ', 'stock', true, '{}', NOW(), NOW()),
(gen_random_uuid(), 'AMZN', 'Amazon.com Inc', 'NASDAQ', 'stock', true, '{}', NOW(), NOW()),
(gen_random_uuid(), 'GOOGL', 'Alphabet Inc Class A', 'NASDAQ', 'stock', true, '{}', NOW(), NOW()),
(gen_random_uuid(), 'HD', 'Home Depot Inc', 'NYSE', 'stock', true, '{}', NOW(), NOW()),
(gen_random_uuid(), 'INTC', 'Intel Corporation', 'NASDAQ', 'stock', true, '{}', NOW(), NOW()),
(gen_random_uuid(), 'JNJ', 'Johnson & Johnson', 'NYSE', 'stock', true, '{}', NOW(), NOW()),
(gen_random_uuid(), 'META', 'Meta Platforms Inc', 'NASDAQ', 'stock', true, '{}', NOW(), NOW()),
(gen_random_uuid(), 'NIO', 'NIO Inc', 'NYSE', 'stock', true, '{}', NOW(), NOW()),
(gen_random_uuid(), 'NVDA', 'NVIDIA Corporation', 'NASDAQ', 'stock', true, '{}', NOW(), NOW()),
(gen_random_uuid(), 'PYPL', 'PayPal Holdings Inc', 'NASDAQ', 'stock', true, '{}', NOW(), NOW()),
(gen_random_uuid(), 'SOFI', 'SoFi Technologies Inc', 'NASDAQ', 'stock', true, '{}', NOW(), NOW()),
(gen_random_uuid(), 'SPY', 'SPDR S&P 500 ETF', 'NYSE', 'stock', true, '{}', NOW(), NOW()),
(gen_random_uuid(), 'T', 'AT&T Inc', 'NYSE', 'stock', true, '{}', NOW(), NOW()),
(gen_random_uuid(), 'V', 'Visa Inc', 'NYSE', 'stock', true, '{}', NOW(), NOW()),
-- Additional momentum trading stocks
(gen_random_uuid(), 'AAPL', 'Apple Inc', 'NASDAQ', 'stock', true, '{}', NOW(), NOW()),
(gen_random_uuid(), 'MSFT', 'Microsoft Corporation', 'NASDAQ', 'stock', true, '{}', NOW(), NOW()),
(gen_random_uuid(), 'TSLA', 'Tesla Inc', 'NASDAQ', 'stock', true, '{}', NOW(), NOW()),
(gen_random_uuid(), 'JPM', 'JPMorgan Chase & Co', 'NYSE', 'stock', true, '{}', NOW(), NOW()),
(gen_random_uuid(), 'AVGO', 'Broadcom Inc', 'NASDAQ', 'stock', true, '{}', NOW(), NOW()),
(gen_random_uuid(), 'MU', 'Micron Technology', 'NASDAQ', 'stock', true, '{}', NOW(), NOW())
ON CONFLICT (ticker) DO NOTHING;

-- Insert crypto symbols
INSERT INTO symbols (id, ticker, name, exchange, asset_type, is_active, metadata_json, created_at, updated_at) VALUES
(gen_random_uuid(), 'BTCUSD', 'Bitcoin', 'CRYPTO', 'crypto', true, '{}', NOW(), NOW()),
(gen_random_uuid(), 'ETHUSD', 'Ethereum', 'CRYPTO', 'crypto', true, '{}', NOW(), NOW()),
(gen_random_uuid(), 'SOLUSD', 'Solana', 'CRYPTO', 'crypto', true, '{}', NOW(), NOW()),
(gen_random_uuid(), 'ADAUSD', 'Cardano', 'CRYPTO', 'crypto', true, '{}', NOW(), NOW()),
(gen_random_uuid(), 'DOGEUSD', 'Dogecoin', 'CRYPTO', 'crypto', true, '{}', NOW(), NOW()),
(gen_random_uuid(), 'MATICUSD', 'Polygon', 'CRYPTO', 'crypto', true, '{}', NOW(), NOW()),
(gen_random_uuid(), 'LINKUSD', 'Chainlink', 'CRYPTO', 'crypto', true, '{}', NOW(), NOW()),
(gen_random_uuid(), 'DOTUSD', 'Polkadot', 'CRYPTO', 'crypto', true, '{}', NOW(), NOW()),
(gen_random_uuid(), 'UNIUSD', 'Uniswap', 'CRYPTO', 'crypto', true, '{}', NOW(), NOW()),
(gen_random_uuid(), 'LTCUSD', 'Litecoin', 'CRYPTO', 'crypto', true, '{}', NOW(), NOW())
ON CONFLICT (ticker) DO NOTHING;