"""
config.py — Loads volume bot settings from .env file.

Volume bot performs alternating buy/sell swaps between USDC.e and your domain
token to generate trading volume. Each swap loses the pool fee + slippage —
budget for this carefully.
"""
import os
from dotenv import load_dotenv
from web3 import Web3

load_dotenv()


def _addr(val: str) -> str:
    return Web3.to_checksum_address(val.strip())


def _float(key: str, default: float) -> float:
    return float(os.getenv(key, str(default)))


def _int(key: str, default: int) -> int:
    return int(os.getenv(key, str(default)))


def _bool(key: str, default: bool) -> bool:
    val = os.getenv(key)
    if val is None:
        return default
    return val.strip().lower() in ("true", "1", "yes")


# ── Wallet ────────────────────────────────────────────────────────────────
MNEMONIC               = os.getenv("MNEMONIC", "").strip()
PRIVATE_KEY            = os.getenv("PRIVATE_KEY", "").strip()
MNEMONIC_ACCOUNT_INDEX = _int("MNEMONIC_ACCOUNT_INDEX", 0)

if not MNEMONIC and not PRIVATE_KEY:
    raise ValueError("Set either MNEMONIC or PRIVATE_KEY in your .env file")

if PRIVATE_KEY and not PRIVATE_KEY.startswith("0x"):
    PRIVATE_KEY = "0x" + PRIVATE_KEY


# ── Network ──────────────────────────────────────────────────────────────
RPC_URL    = os.getenv("RPC_URL",    "https://doma.drpc.org")
RPC_BACKUP = os.getenv("RPC_BACKUP", "https://rpc.doma.xyz")
CHAIN_ID   = _int("CHAIN_ID", 97477)


# ── Doma V3 contracts (shared across all Doma launchpad tokens) ──────────
USDCE_ADDRESS    = _addr(os.getenv("USDCE_ADDRESS",    "0x31EEf89D5215C305304a2fA5376a1f1b6C5dc477"))
UNIVERSAL_ROUTER = _addr(os.getenv("UNIVERSAL_ROUTER", "0x5089863E97196773038f98459262D866f2281f58"))


# ── Target token + pool (REQUIRED — set in .env) ─────────────────────────
# Your domain token address (from your domain's V3 graduation)
TOKEN_ADDRESS = _addr(os.getenv("TOKEN_ADDRESS", "0x0000000000000000000000000000000000000000"))
TOKEN_SYMBOL  = os.getenv("TOKEN_SYMBOL", "TOKEN")

# The V3 pool address for USDC.e/your-token
POOL_ADDRESS  = _addr(os.getenv("POOL_ADDRESS",  "0x0000000000000000000000000000000000000000"))

# Pool fee tier (Uniswap V3 units: 100=0.01%, 500=0.05%, 3000=0.30%, 10000=1.00%)
POOL_FEE      = _int("POOL_FEE", 500)

# Token decimals — most Doma launchpad tokens are 6; ETH/WETH is 18
TOKEN_DECIMALS = _int("TOKEN_DECIMALS", 6)
USDCE_DECIMALS = _int("USDCE_DECIMALS", 6)


# ── Volume generation strategy ───────────────────────────────────────────
# Each cycle does ONE swap (alternates direction).
# Random jitter on size and interval makes the activity look more natural.

# Swap size range (USD). Bot picks random value between min and max each cycle.
SWAP_SIZE_USD_MIN = _float("SWAP_SIZE_USD_MIN", 5.0)
SWAP_SIZE_USD_MAX = _float("SWAP_SIZE_USD_MAX", 25.0)

# Time between swaps (seconds). Random jitter between min and max.
SWAP_INTERVAL_SEC_MIN = _int("SWAP_INTERVAL_SEC_MIN", 60)
SWAP_INTERVAL_SEC_MAX = _int("SWAP_INTERVAL_SEC_MAX", 300)

# Slippage tolerance — bot aborts swap if expected output is worse than this
MAX_SLIPPAGE_PCT = _float("MAX_SLIPPAGE_PCT", 0.005)   # 0.5%


# ── Safety guards ────────────────────────────────────────────────────────
# Daily loss budget — bot halts for the day if cumulative loss exceeds this.
# Each round-trip swap costs ~2× pool fee. At 0.05% pool with $10 swaps:
#   - 100 swaps = $1000 volume = $1 in fees + slippage
# Budget accordingly.
DAILY_LOSS_BUDGET_USD = _float("DAILY_LOSS_BUDGET_USD", 5.0)

# Minimum pool TVL — bot won't swap if pool is too thin (avoids huge slippage)
MIN_POOL_TVL_USD = _float("MIN_POOL_TVL_USD", 5000.0)

# Maximum % of pool TVL per swap — keeps slippage low
MAX_SWAP_PCT_OF_TVL = _float("MAX_SWAP_PCT_OF_TVL", 0.005)   # 0.5%

# If estimated swap impact exceeds this, skip the swap
MAX_SWAP_IMPACT_BPS = _float("MAX_SWAP_IMPACT_BPS", 50.0)   # 0.5%


# ── Mode ─────────────────────────────────────────────────────────────────
DRY_RUN     = _bool("DRY_RUN", True)
LOG_LEVEL   = os.getenv("LOG_LEVEL", "INFO")


# ── Sanity checks ────────────────────────────────────────────────────────
if TOKEN_ADDRESS == "0x0000000000000000000000000000000000000000":
    raise ValueError("TOKEN_ADDRESS not set in .env — see README for setup")
if POOL_ADDRESS == "0x0000000000000000000000000000000000000000":
    raise ValueError("POOL_ADDRESS not set in .env — see README for setup")
if SWAP_SIZE_USD_MIN > SWAP_SIZE_USD_MAX:
    raise ValueError("SWAP_SIZE_USD_MIN must be ≤ SWAP_SIZE_USD_MAX")
if SWAP_INTERVAL_SEC_MIN > SWAP_INTERVAL_SEC_MAX:
    raise ValueError("SWAP_INTERVAL_SEC_MIN must be ≤ SWAP_INTERVAL_SEC_MAX")
