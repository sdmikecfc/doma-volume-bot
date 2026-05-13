"""
shared.py — Wallet loading, RPC connection, ABIs, logging.
"""
import sys
from datetime import datetime

from eth_account import Account
from web3 import Web3

import config


# ── Logging ───────────────────────────────────────────────────────────────

def log(level: str, msg: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"{ts}  {level:<5} {msg}", flush=True)


def info(msg):  log("INFO",  msg)
def warn(msg):  log("WARN",  msg)
def err(msg):   log("ERROR", msg)


# ── Web3 connection ───────────────────────────────────────────────────────

def connect() -> Web3:
    """Try primary RPC, fall back to backup."""
    for url in (config.RPC_URL, config.RPC_BACKUP):
        if not url:
            continue
        w3 = Web3(Web3.HTTPProvider(url, request_kwargs={"timeout": 10}))
        if w3.is_connected():
            cid = w3.eth.chain_id
            if cid != config.CHAIN_ID:
                warn(f"RPC {url} returned chain_id={cid}, expected {config.CHAIN_ID}")
                continue
            info(f"Connected to RPC: chain_id={cid}")
            return w3
    err("Could not connect to any RPC")
    sys.exit(1)


# ── Wallet ────────────────────────────────────────────────────────────────

def load_wallet() -> tuple[str, str]:
    """Return (address, private_key_hex)."""
    if config.MNEMONIC:
        Account.enable_unaudited_hdwallet_features()
        acct = Account.from_mnemonic(
            config.MNEMONIC,
            account_path=f"m/44'/60'/0'/0/{config.MNEMONIC_ACCOUNT_INDEX}",
        )
    elif config.PRIVATE_KEY:
        acct = Account.from_key(config.PRIVATE_KEY)
    else:
        err("No MNEMONIC or PRIVATE_KEY in .env")
        sys.exit(1)
    return acct.address, acct.key.hex()


# ── ABIs ──────────────────────────────────────────────────────────────────

ERC20_ABI = [
    {"name": "balanceOf", "type": "function", "stateMutability": "view",
     "inputs": [{"name": "a", "type": "address"}],
     "outputs": [{"name": "", "type": "uint256"}]},
    {"name": "decimals", "type": "function", "stateMutability": "view",
     "inputs": [], "outputs": [{"name": "", "type": "uint8"}]},
    {"name": "symbol", "type": "function", "stateMutability": "view",
     "inputs": [], "outputs": [{"name": "", "type": "string"}]},
    {"name": "approve", "type": "function", "stateMutability": "nonpayable",
     "inputs": [{"name": "spender", "type": "address"},
                {"name": "amount",  "type": "uint256"}],
     "outputs": [{"name": "", "type": "bool"}]},
    {"name": "allowance", "type": "function", "stateMutability": "view",
     "inputs": [{"name": "owner",   "type": "address"},
                {"name": "spender", "type": "address"}],
     "outputs": [{"name": "", "type": "uint256"}]},
]

POOL_ABI = [
    {"name": "slot0", "type": "function", "stateMutability": "view",
     "inputs": [], "outputs": [
        {"name": "sqrtPriceX96",               "type": "uint160"},
        {"name": "tick",                       "type": "int24"},
        {"name": "observationIndex",           "type": "uint16"},
        {"name": "observationCardinality",     "type": "uint16"},
        {"name": "observationCardinalityNext", "type": "uint16"},
        {"name": "feeProtocol",                "type": "uint8"},
        {"name": "unlocked",                   "type": "bool"},
     ]},
    {"name": "token0", "type": "function", "stateMutability": "view",
     "inputs": [], "outputs": [{"name": "", "type": "address"}]},
    {"name": "token1", "type": "function", "stateMutability": "view",
     "inputs": [], "outputs": [{"name": "", "type": "address"}]},
    {"name": "fee", "type": "function", "stateMutability": "view",
     "inputs": [], "outputs": [{"name": "", "type": "uint24"}]},
    {"name": "liquidity", "type": "function", "stateMutability": "view",
     "inputs": [], "outputs": [{"name": "", "type": "uint128"}]},
]
