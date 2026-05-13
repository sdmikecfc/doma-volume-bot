"""
swap_executor.py — Atomic swap via Permit2 + Universal Router on Doma.

Same proven pattern used by every production bot on Doma. Tokens are pulled
during the swap (atomic) — never sit in the router waiting to be MEV'd.

ONE-TIME SETUP per token (idempotent — bot will run automatically on startup):
  1. ERC20.approve(token → Permit2, MAX_UINT256)
  2. Permit2.approve(token, ROUTER, MAX_UINT160, far_future_expiration)

PER SWAP:
  router.execute(
      commands=[V3_SWAP_EXACT_IN],
      inputs=[encode(recipient, amountIn, amountOutMin, path, payerIsUser=true)],
      deadline,
  )
"""
import time

from eth_abi import encode
from eth_abi.packed import encode_packed
from web3 import Web3

import config
from shared import info, warn, err, ERC20_ABI


# Canonical Permit2 address (same on every chain that uses Uniswap V3)
PERMIT2_ADDRESS = "0x000000000022D473030F116dDEE9F6B43aC78BA3"

MAX_UINT256        = 2 ** 256 - 1
MAX_UINT160        = 2 ** 160 - 1
PERMIT2_EXPIRATION = 4_102_444_800   # 2100-01-01 — effectively never
CMD_V3_SWAP_EXACT_IN = 0x00


ROUTER_ABI = [{
    "name": "execute", "type": "function", "stateMutability": "payable",
    "inputs": [
        {"name": "commands", "type": "bytes"},
        {"name": "inputs",   "type": "bytes[]"},
        {"name": "deadline", "type": "uint256"},
    ],
    "outputs": [],
}]

PERMIT2_ABI = [
    {"name": "approve", "type": "function", "stateMutability": "nonpayable",
     "inputs": [
         {"name": "token",      "type": "address"},
         {"name": "spender",    "type": "address"},
         {"name": "amount",     "type": "uint160"},
         {"name": "expiration", "type": "uint48"},
     ],
     "outputs": []},
    {"name": "allowance", "type": "function", "stateMutability": "view",
     "inputs": [
         {"name": "user",    "type": "address"},
         {"name": "token",   "type": "address"},
         {"name": "spender", "type": "address"},
     ],
     "outputs": [
         {"name": "amount",     "type": "uint160"},
         {"name": "expiration", "type": "uint48"},
         {"name": "nonce",      "type": "uint48"},
     ]},
]

# Transfer event signature for receipt parsing
TRANSFER_SIG = "ddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"


def _send_tx(w3, tx, private_key, label: str):
    """Sign, send, wait. Returns receipt or None."""
    try:
        signed = w3.eth.account.sign_transaction(tx, private_key)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        info(f"  {label} tx: 0x{tx_hash.hex().lstrip('0x')}")
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
        if receipt.status != 1:
            err(f"  {label} FAILED (status=0)")
            return None
        info(f"  {label} ✓ block {receipt.blockNumber}")
        return receipt
    except Exception as e:
        err(f"  {label} exception: {e}")
        return None


def _parse_received_from_receipt(receipt, token_out: str, wallet: str) -> int:
    """Parse Transfer logs from receipt to authoritatively get amount received."""
    token_lower  = token_out.lower()
    wallet_lower = wallet.lower()
    total = 0
    for log in receipt.get("logs", []):
        topics = log.get("topics", [])
        if len(topics) < 3:
            continue
        sig = topics[0].hex().lower().lstrip("0x")
        if sig != TRANSFER_SIG:
            continue
        contract = log.get("address", "").lower()
        if contract != token_lower:
            continue
        to_addr = "0x" + topics[2].hex()[-40:]
        if to_addr.lower() != wallet_lower:
            continue
        data = log.get("data", b"\x00")
        amount = int(data.hex(), 16) if isinstance(data, (bytes, bytearray)) else int(data, 16)
        total += amount
    return total


def ensure_erc20_to_permit2(w3, wallet, private_key, token_addr: str, gas_price: int) -> bool:
    """ERC20.approve(token → Permit2, MAX). Idempotent."""
    token = w3.eth.contract(
        address=Web3.to_checksum_address(token_addr), abi=ERC20_ABI
    )
    permit2 = Web3.to_checksum_address(PERMIT2_ADDRESS)

    current = token.functions.allowance(wallet, permit2).call()
    if current >= MAX_UINT256 // 2:
        return True

    info(f"  Approving {token_addr[:10]} → Permit2 (one-time)")
    nonce = w3.eth.get_transaction_count(wallet, "pending")
    try:
        gas_est   = token.functions.approve(permit2, MAX_UINT256).estimate_gas({"from": wallet})
        gas_limit = int(gas_est * 1.5)
    except Exception:
        gas_limit = 80_000

    tx = token.functions.approve(permit2, MAX_UINT256).build_transaction({
        "from": wallet, "nonce": nonce, "gas": gas_limit,
        "gasPrice": gas_price, "chainId": config.CHAIN_ID,
    })
    return _send_tx(w3, tx, private_key, "ERC20→Permit2") is not None


def ensure_permit2_to_router(w3, wallet, private_key, token_addr: str, gas_price: int) -> bool:
    """Permit2.approve(token, ROUTER, MAX, expires_2100). Idempotent."""
    permit2 = w3.eth.contract(
        address=Web3.to_checksum_address(PERMIT2_ADDRESS), abi=PERMIT2_ABI
    )
    router = Web3.to_checksum_address(config.UNIVERSAL_ROUTER)

    current = permit2.functions.allowance(
        wallet, Web3.to_checksum_address(token_addr), router
    ).call()
    cur_amount, cur_expiration, _ = current

    if cur_amount >= MAX_UINT160 // 2 and cur_expiration > int(time.time()) + 86400:
        return True

    info(f"  Approving Permit2 {token_addr[:10]} → Router (one-time)")
    nonce = w3.eth.get_transaction_count(wallet, "pending")
    try:
        gas_est = permit2.functions.approve(
            Web3.to_checksum_address(token_addr), router,
            MAX_UINT160, PERMIT2_EXPIRATION
        ).estimate_gas({"from": wallet})
        gas_limit = int(gas_est * 1.5)
    except Exception:
        gas_limit = 80_000

    tx = permit2.functions.approve(
        Web3.to_checksum_address(token_addr), router,
        MAX_UINT160, PERMIT2_EXPIRATION
    ).build_transaction({
        "from": wallet, "nonce": nonce, "gas": gas_limit,
        "gasPrice": gas_price, "chainId": config.CHAIN_ID,
    })
    return _send_tx(w3, tx, private_key, "Permit2→Router") is not None


def ensure_swap_setup(w3, wallet, private_key, token_addr: str, gas_price: int) -> bool:
    """Both approvals. Idempotent — safe to call before every swap."""
    if not ensure_erc20_to_permit2(w3, wallet, private_key, token_addr, gas_price):
        return False
    if not ensure_permit2_to_router(w3, wallet, private_key, token_addr, gas_price):
        return False
    return True


def estimate_amount_out(sqrt_price_x96: int, amount_in_raw: int, token_in_is_token0: bool) -> int:
    """Estimate output from slot0 price (no slippage). For min-out calculation."""
    if sqrt_price_x96 == 0:
        return 0
    if token_in_is_token0:
        return (amount_in_raw * sqrt_price_x96 * sqrt_price_x96) // (2 ** 192)
    else:
        return (amount_in_raw * (2 ** 192)) // (sqrt_price_x96 * sqrt_price_x96)


def swap_exact_in(
    w3, wallet, private_key,
    token_in: str, token_out: str,
    amount_in_raw: int, min_out_raw: int,
    pool_fee: int, gas_price: int,
) -> tuple[bool, int]:
    """
    Atomic swap via Universal Router. Returns (success, received_raw).
    Caller must have ensure_swap_setup(token_in) at least once.
    """
    if amount_in_raw < 100:
        info(f"  swap skipped: amount {amount_in_raw} too small")
        return True, 0

    # Build V3 path: tokenIn + fee(uint24) + tokenOut
    path = encode_packed(
        ["address", "uint24", "address"],
        [Web3.to_checksum_address(token_in), pool_fee,
         Web3.to_checksum_address(token_out)],
    )

    # V3_SWAP_EXACT_IN input: (recipient, amountIn, amountOutMin, path, payerIsUser=true)
    swap_input = encode(
        ["address", "uint256", "uint256", "bytes", "bool"],
        [wallet, amount_in_raw, min_out_raw, path, True],
    )

    router = w3.eth.contract(
        address=Web3.to_checksum_address(config.UNIVERSAL_ROUTER), abi=ROUTER_ABI
    )
    deadline = int(time.time()) + 600

    nonce = w3.eth.get_transaction_count(wallet, "pending")
    try:
        gas_est = router.functions.execute(
            bytes([CMD_V3_SWAP_EXACT_IN]), [swap_input], deadline
        ).estimate_gas({"from": wallet})
        gas_limit = int(gas_est * 1.5)
    except Exception as e:
        warn(f"  swap gas estimate failed: {e} — using fallback")
        gas_limit = 400_000

    tx = router.functions.execute(
        bytes([CMD_V3_SWAP_EXACT_IN]), [swap_input], deadline
    ).build_transaction({
        "from": wallet, "nonce": nonce, "gas": gas_limit,
        "gasPrice": gas_price, "chainId": config.CHAIN_ID, "value": 0,
    })

    receipt = _send_tx(w3, tx, private_key, "swap")
    if receipt is None:
        return False, 0

    # Parse Transfer log from receipt (authoritative; RPC balanceOf can lag)
    received = _parse_received_from_receipt(receipt, token_out, wallet)
    if received <= 0:
        # Fallback: read balance
        token_out_c = w3.eth.contract(
            address=Web3.to_checksum_address(token_out), abi=ERC20_ABI
        )
        received = token_out_c.functions.balanceOf(wallet).call()

    if received <= 0:
        err(f"  swap parsed 0 tokens received")
        return False, 0

    info(f"  swap ✓ received {received} (raw)")
    return True, received
