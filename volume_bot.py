"""
volume_bot.py — Generate trading volume on your Doma domain token's V3 pool
via alternating buy/sell swaps.

PURPOSE
  Domain projects sometimes need genuine on-chain trading volume — for
  leaderboards, perception, or attracting bot/aggregator routing. This bot
  performs small back-and-forth swaps with built-in safety guards.

COST
  Every round-trip swap costs ~2× the pool fee + slippage.
  - 0.05% pool: ~$0.10 per $100 of round-trip volume
  - 0.30% pool: ~$0.60 per $100 of round-trip volume
  Budget for this. Bot enforces a daily loss cap (DAILY_LOSS_BUDGET_USD).

SAFETY
  - Daily loss budget — bot halts for the day if exceeded
  - Pool TVL minimum — skip swap if pool too thin
  - Max swap impact — skip if price impact too high
  - Pre-swap simulation — uses slot0 to compute expected output
  - Slippage tolerance — abort if quoted output is worse than expected

USAGE
  1. Copy .env.example to .env, fill in MNEMONIC + TOKEN_ADDRESS + POOL_ADDRESS
  2. Send ~$200 USDC.e + ~$200 worth of your token to the wallet
  3. Run:  python3 volume_bot.py --dry-run    (no real transactions)
  4. When confident:  python3 volume_bot.py
"""
import random
import sys
import time
import traceback
from decimal import Decimal, getcontext

from web3 import Web3

import config
from shared import (
    connect, load_wallet, info, warn, err, ERC20_ABI, POOL_ABI,
)
from swap_executor import (
    ensure_swap_setup, swap_exact_in, estimate_amount_out,
)
import state


getcontext().prec = 50

DRY_RUN = "--dry-run" in sys.argv or config.DRY_RUN


def read_pool_state(w3, pool_address: str) -> dict:
    """Returns sqrt_price_x96, current_price (USDC.e per token), liquidity,
    token_is_token0 (is OUR token token0?)."""
    pool = w3.eth.contract(
        address=Web3.to_checksum_address(pool_address), abi=POOL_ABI
    )
    t0 = pool.functions.token0().call().lower()
    s0 = pool.functions.slot0().call()
    liq = pool.functions.liquidity().call()
    sqrt_p = s0[0]
    tick = s0[1]

    token_is_token0 = (config.TOKEN_ADDRESS.lower() == t0)

    # USDC.e per token (human-readable)
    if sqrt_p == 0:
        price = 0.0
    else:
        raw = Decimal(sqrt_p) ** 2 / Decimal(2 ** 192)
        multiplier = Decimal(10 ** config.TOKEN_DECIMALS) / Decimal(10 ** config.USDCE_DECIMALS)
        if token_is_token0:
            price = float(raw * multiplier)
        else:
            price = float(multiplier / raw) if raw else 0.0

    return {
        "sqrt_price_x96": sqrt_p,
        "tick": tick,
        "price": price,
        "liquidity": liq,
        "token_is_token0": token_is_token0,
    }


def read_pool_tvl_usd(w3, pool_address: str, price: float) -> float:
    """Approx TVL by reading both tokens' balances in the pool contract."""
    pool_addr = Web3.to_checksum_address(pool_address)
    usdce = w3.eth.contract(
        address=Web3.to_checksum_address(config.USDCE_ADDRESS), abi=ERC20_ABI
    )
    token = w3.eth.contract(
        address=Web3.to_checksum_address(config.TOKEN_ADDRESS), abi=ERC20_ABI
    )
    u_raw = usdce.functions.balanceOf(pool_addr).call()
    t_raw = token.functions.balanceOf(pool_addr).call()
    u_usd = u_raw / 10 ** config.USDCE_DECIMALS
    t_usd = (t_raw / 10 ** config.TOKEN_DECIMALS) * price
    return u_usd + t_usd


def safety_check(con, pool_tvl_usd: float, swap_size_usd: float) -> tuple[bool, str]:
    """Returns (ok, reason). False if any safety check fails."""
    # 1. Daily loss budget
    today = state.get_today_totals(con)
    if today["cost_usd"] >= config.DAILY_LOSS_BUDGET_USD:
        return False, (f"Daily loss ${today['cost_usd']:.4f} >= budget "
                       f"${config.DAILY_LOSS_BUDGET_USD:.4f}")

    # 2. Pool TVL minimum
    if pool_tvl_usd < config.MIN_POOL_TVL_USD:
        return False, (f"Pool TVL ${pool_tvl_usd:.2f} < minimum "
                       f"${config.MIN_POOL_TVL_USD:.2f}")

    # 3. Max swap % of TVL
    max_swap = pool_tvl_usd * config.MAX_SWAP_PCT_OF_TVL
    if swap_size_usd > max_swap:
        return False, (f"Swap ${swap_size_usd:.2f} > "
                       f"{config.MAX_SWAP_PCT_OF_TVL*100:.1f}% of pool "
                       f"(${max_swap:.2f})")

    return True, ""


def pick_direction(con) -> str:
    """Alternate: if last was buy, next is sell, and vice versa."""
    last = state.get_last_direction(con)
    if last == "buy":
        return "sell"
    return "buy"   # default first swap


def execute_one_swap(w3, wallet, pkey, con, pool, direction: str,
                     swap_size_usd: float) -> bool:
    """Execute a single swap (USDC.e ↔ token). Returns True if success."""
    gas_price = int(w3.eth.gas_price * 1.5)

    if direction == "buy":
        # USDC.e → token
        token_in       = config.USDCE_ADDRESS
        token_out      = config.TOKEN_ADDRESS
        decimals_in    = config.USDCE_DECIMALS
        decimals_out   = config.TOKEN_DECIMALS
        amount_in_raw  = int(swap_size_usd * 10 ** decimals_in)
        # tokenIn=USDC.e; token_in_is_token0 = NOT token_is_token0
        token_in_is_token0 = not pool["token_is_token0"]
    else:
        # token → USDC.e
        token_in       = config.TOKEN_ADDRESS
        token_out      = config.USDCE_ADDRESS
        decimals_in    = config.TOKEN_DECIMALS
        decimals_out   = config.USDCE_DECIMALS
        amount_in_raw  = int((swap_size_usd / pool["price"]) * 10 ** decimals_in)
        token_in_is_token0 = pool["token_is_token0"]

    # Check we have enough balance
    in_c = w3.eth.contract(
        address=Web3.to_checksum_address(token_in), abi=ERC20_ABI
    )
    bal = in_c.functions.balanceOf(wallet).call()
    if bal < amount_in_raw:
        warn(f"  insufficient {token_in[:10]} balance "
             f"({bal/(10**decimals_in):.4f} < {amount_in_raw/(10**decimals_in):.4f})")
        return False

    # Estimate output for slippage protection + impact check
    expected_out = estimate_amount_out(
        pool["sqrt_price_x96"], amount_in_raw, token_in_is_token0
    )
    min_out_raw = int(expected_out * (1 - config.MAX_SLIPPAGE_PCT))

    if DRY_RUN:
        info(f"  [DRY RUN] {direction}: {amount_in_raw} (in) → expect {expected_out} (out)")
        return True

    # Ensure approvals
    if not ensure_swap_setup(w3, wallet, pkey, token_in, gas_price):
        err(f"  approval setup failed for {token_in[:10]}")
        return False

    # Execute swap
    ok, received = swap_exact_in(
        w3, wallet, pkey, token_in, token_out,
        amount_in_raw, min_out_raw, config.POOL_FEE, gas_price,
    )
    if not ok:
        err(f"  swap failed")
        return False

    # Compute USD values for logging
    if direction == "buy":
        amount_in_usd  = amount_in_raw / 10 ** decimals_in       # USDC.e at $1
        amount_out_usd = (received     / 10 ** decimals_out) * pool["price"]
    else:
        amount_in_usd  = (amount_in_raw / 10 ** decimals_in) * pool["price"]
        amount_out_usd = received     / 10 ** decimals_out

    state.record_swap(con,
        direction=direction,
        amount_in_raw=amount_in_raw, amount_out_raw=received,
        amount_in_usd=amount_in_usd, amount_out_usd=amount_out_usd,
        pool_price=pool["price"], tx_hash=None,
        status="OK",
    )

    cost = amount_in_usd - amount_out_usd
    info(f"  swap ✓ {direction}: in=${amount_in_usd:.4f} out=${amount_out_usd:.4f} cost=${cost:.4f}")
    return True


def main():
    info("=" * 70)
    info(f"  Doma Volume Bot — {config.TOKEN_SYMBOL}")
    info("=" * 70)
    info(f"  Pool:         {config.POOL_ADDRESS}")
    info(f"  Fee tier:     {config.POOL_FEE/10000:.3f}%")
    info(f"  Swap size:    ${config.SWAP_SIZE_USD_MIN}-{config.SWAP_SIZE_USD_MAX}")
    info(f"  Interval:     {config.SWAP_INTERVAL_SEC_MIN}-{config.SWAP_INTERVAL_SEC_MAX}s")
    info(f"  Daily budget: ${config.DAILY_LOSS_BUDGET_USD}")
    info(f"  DRY RUN:      {DRY_RUN}")

    w3 = connect()
    wallet, pkey = load_wallet()
    info(f"  Wallet:       {wallet}")

    con = state.get_db()

    while True:
        try:
            pool = read_pool_state(w3, config.POOL_ADDRESS)
            if pool["price"] <= 0:
                warn("Bad pool price, retrying in 30s")
                time.sleep(30)
                continue

            pool_tvl = read_pool_tvl_usd(w3, config.POOL_ADDRESS, pool["price"])

            # Random swap size + interval for natural appearance
            swap_size = random.uniform(
                config.SWAP_SIZE_USD_MIN, config.SWAP_SIZE_USD_MAX
            )
            interval = random.randint(
                config.SWAP_INTERVAL_SEC_MIN, config.SWAP_INTERVAL_SEC_MAX
            )

            # Safety check
            ok, reason = safety_check(con, pool_tvl, swap_size)
            if not ok:
                warn(f"  safety check failed: {reason}")
                if "Daily loss" in reason:
                    info(f"  budget exceeded — sleeping 1h then retrying tomorrow")
                    time.sleep(3600)
                else:
                    time.sleep(interval)
                continue

            direction = pick_direction(con)
            today     = state.get_today_totals(con)

            info(f"[#{today['swaps_count']+1}] direction={direction}  "
                 f"size=${swap_size:.2f}  price=${pool['price']:.6f}  "
                 f"tvl=${pool_tvl:.0f}  daily=${today['volume_usd']:.2f}vol/"
                 f"${today['cost_usd']:.4f}cost")

            execute_one_swap(w3, wallet, pkey, con, pool, direction, swap_size)

            info(f"  sleeping {interval}s...")
            time.sleep(interval)

        except KeyboardInterrupt:
            info("\nStopped by user.")
            break
        except Exception as e:
            err(f"main loop exception: {e}")
            traceback.print_exc()
            time.sleep(30)


if __name__ == "__main__":
    main()
