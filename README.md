# Doma Volume Bot

Generate trading volume on your Doma domain token's V3 pool via alternating buy/sell swaps.

## Why use this?

- **Leaderboard farming** — Doma has leaderboards rewarding tokens with high volume
- **Perception / signals** — Your token appears more actively traded
- **Aggregator routing** — DEX routers favor pools with consistent activity

## Cost

Every round-trip swap costs ~2× the pool fee + slippage.

- **0.05% pool**: ~$0.10 per $100 of round-trip volume
- **0.30% pool**: ~$0.60 per $100 of round-trip volume

The bot has a `DAILY_LOSS_BUDGET_USD` setting that halts trading for the day if exceeded.

## Safety guards

- Daily loss budget (halts when exceeded)
- Minimum pool TVL check (skips dead pools)
- Max % of pool TVL per swap (limits slippage)
- Pre-swap price impact estimate
- Slippage tolerance per swap
- Dedicated wallet (never reuse your main wallet)

## Quick start

```bash
# 1. Install
pip install -r requirements.txt

# 2. Configure
cp .env.example .env
nano .env   # fill in MNEMONIC, TOKEN_ADDRESS, POOL_ADDRESS

# 3. Test (no real transactions)
python3 volume_bot.py --dry-run

# 4. When confident, run live
python3 volume_bot.py
```

## Where to find your TOKEN_ADDRESS + POOL_ADDRESS

1. Go to https://doma.xyz/explore
2. Search for your domain token
3. Click the V3 pool — you'll see the pool address and token addresses

## Production: run under supervisor

See `INSTALL.md` for full setup instructions including:
- Generating a dedicated wallet
- Funding the wallet
- Running under supervisor for auto-restart
- Monitoring + emergency stop

## License

MIT. Use at your own risk. Bot performs real swaps that lose real money to fees.
