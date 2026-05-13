# Doma Volume Bot — Complete Setup Guide

A start-to-finish guide for running an automated buy/sell bot that generates trading volume on your domain token's V3 pool on Doma. Written for community members with basic command-line skills. Every step you need is in this document — no jumping between docs, no guessing.

---

## What this does (in one paragraph)

The Doma Volume Bot performs alternating small buy and sell swaps between USDC.e and your domain token on the same Uniswap V3 pool. Each swap is randomized in size and timing so the activity looks natural rather than mechanical. The result is a steady stream of real on-chain volume on your token — useful for leaderboards, perception, and for getting picked up by DEX aggregators that prefer pools with consistent activity. The bot is **not a profit-making bot**: every swap costs the pool fee plus a tiny amount of slippage, and you are paying for the volume you generate.

---

## What it costs (round-trip math)

A "round-trip" is one buy followed by one sell of equivalent size. Each leg pays the pool fee, so a round-trip costs about **2× the pool fee**, plus a sliver of slippage.

| Pool fee tier | Cost per $100 round-trip volume | $1,000 daily volume costs | $10,000 daily volume costs |
|---|---|---|---|
| 0.01% | ~$0.02 | ~$0.20 / day | ~$2.00 / day |
| 0.05% (most Doma tokens) | ~$0.10 | ~$1.00 / day | ~$10.00 / day |
| 0.30% | ~$0.60 | ~$6.00 / day | ~$60.00 / day |
| 1.00% | ~$2.00 | ~$20.00 / day | ~$200.00 / day |

Gas on Doma is sub-Gwei, so transaction fees are negligible — typically a fraction of a cent per swap. Your real cost is the pool fee. The bot enforces a daily USD loss cap (`DAILY_LOSS_BUDGET_USD`) and stops trading for the rest of the calendar day if it's exceeded. Setting this number correctly is the single most important config decision you will make.

---

## Risks — read this before doing anything else

- **The bot loses money by design.** Every swap costs the pool fee. You are buying volume, not earning it.
- **You must use a fresh wallet.** Never put the bot's seed phrase or private key into anything you also use for real holdings. If the host is compromised, that wallet is gone.
- **Wash trading on your own token may upset your community.** Some users will see steady on-chain volume as a sign of organic interest. Be honest if asked.
- **Don't run this while LPing the same pool.** You'd be paying fees to your own LP position, which is just churn — and your LP rebalancing will partly offset the volume the bot is trying to generate.
- **A bad config can drain the wallet fast.** Read this guide end-to-end before running anything live. Use `DRY_RUN=true` for the first run, always.
- **Doma's gas is cheap, but not free.** Keep a small ETH balance in the bot wallet (a few thousandths of an ETH is plenty for thousands of transactions).
- **There is no "off switch" beyond stopping the process.** If you need to pull funds out fast, you'll stop the bot and manually move tokens — there is no remote kill UI.

---

## Prerequisites

You need:

1. **A computer that stays on.** A $4–$6/month Linux VPS from DigitalOcean, Hetzner, Vultr, or similar is by far the easiest path. Your laptop also works, but it must stay awake and online 24/7 for the bot to run continuously. Windows is supported but slightly more work — this guide focuses on Linux/macOS commands and notes Windows variations where they matter.
2. **Python 3.10 or newer**, with `pip` and `venv` available.
3. **A web browser** to access [https://doma.xyz/explore](https://doma.xyz/explore) and look up your token's pool address and fee tier.
4. **A small amount of USD-equivalent crypto** to fund a fresh wallet. Concretely:
   - About **$50–$200 in USDC.e** on Doma chain (start small).
   - About **$50–$200 worth of your domain token** on Doma chain.
   - About **0.001 ETH** on Doma chain for gas. This will last for thousands of transactions.
5. **About 30–60 minutes** to walk through this guide end-to-end the first time.

---

## Part 1: Generate a dedicated wallet

This is the single most important step. **Do not skip it. Do not reuse an existing wallet.** The bot needs a private key on disk — if your VPS is ever compromised, that key is gone, and so is everything in the wallet. The way to make that survivable is to ensure the wallet only ever holds the small amount the bot needs.

### Option A — Generate a new wallet in MetaMask (easiest for non-technical users)

1. Open MetaMask.
2. Click the account selector at the top.
3. Choose **Add account or hardware wallet** → **Add a new account**. (This creates a new account inside your existing seed phrase — convenient but tied to your existing wallet's seed. **Do not do this** if you want full isolation.)
4. For full isolation, instead choose **Add account or hardware wallet** → **Import account** later, or — better — install a second instance of MetaMask in a different browser profile and use **Create a new wallet** to generate a brand new seed phrase from scratch. Write the seed phrase down on paper and store it somewhere safe. **Do not screenshot it. Do not put it in cloud storage.**
5. Copy the address of the new account. This is the address you'll fund.

### Option B — Generate a wallet from the command line (recommended if you're comfortable with the terminal)

This generates a fresh BIP-39 mnemonic that has never touched any other wallet. Run this on your local laptop, **not** on the VPS:

```bash
pip install mnemonic eth-account
python3 -c "
from mnemonic import Mnemonic
from eth_account import Account
Account.enable_unaudited_hdwallet_features()
m = Mnemonic('english').generate(strength=128)
acct = Account.from_mnemonic(m, account_path=\"m/44'/60'/0'/0/0\")
print('MNEMONIC:', m)
print('ADDRESS: ', acct.address)
"
```

This will print:

```
MNEMONIC: word1 word2 word3 ... word12
ADDRESS:  0xAbCd...1234
```

**Write the mnemonic down on paper.** This is the only backup. If you lose it and lose your config file, the funds in this wallet are gone forever.

### What "dedicated" actually means

A dedicated wallet means:

- The seed phrase has never been entered into any other application, exchange, or wallet.
- You will only ever fund this wallet with the small amount the bot needs (start with $50–$200 of each side, plus ~$5 of ETH for gas).
- You are mentally prepared to consider this wallet "burned" if the host is ever compromised.

**Do not** put your main MetaMask seed phrase into the bot's `.env` file. Even if you're certain your VPS is secure, this practice puts a single typo or git mistake away from leaking your entire portfolio.

---

## Part 2: Get a server (recommended) or use your own computer

The bot is a long-running Python process. It needs to stay awake 24/7 to generate continuous volume. You have three realistic options:

### Option A — Cheap Linux VPS (recommended)

Providers and starting prices as a rough guide (verify current pricing):

- **Hetzner** — CX22 instance, around €4/month
- **DigitalOcean** — basic droplet, around $4–$6/month
- **Vultr** — regular cloud compute, around $3–$6/month
- **Linode (Akamai)** — Nanode 1GB, around $5/month

Any Linux VPS with 1 GB RAM and a few GB of disk will run this bot comfortably. Pick whichever provider you can pay easily and which has a region near you (lower RPC latency = faster swaps, but Doma RPCs are global so this matters less than you'd think).

After you create the VPS:

```bash
# SSH from your laptop
ssh root@YOUR.VPS.IP.ADDRESS

# Update packages (Debian/Ubuntu)
apt update && apt upgrade -y

# Install Python and supporting tools
apt install -y python3 python3-pip python3-venv git supervisor
```

If the VPS uses a non-root user (recommended for security), prefix `apt` commands with `sudo`.

### Option B — Always-on Mac or Linux desktop at home

Works fine. Ensure:

- Sleep is disabled while the bot is running (on macOS, **System Settings → Lock Screen → Prevent automatic sleeping when the display is off** = on).
- Your home internet is reliable.
- You're OK with the laptop fan running and the noise.

You can skip the supervisor section later in this guide and instead use a `screen` or `tmux` session, or `launchd` (macOS) / `systemd` (Linux) to keep the bot up.

### Option C — Windows desktop

The bot runs on Windows but you'll lose the easy supervisor setup. You can install Python from [python.org](https://www.python.org) and then run the bot inside PowerShell. To keep it running:

- Use the Windows **Task Scheduler** to start `python3 volume_bot.py` at user logon, or
- Run it manually in a PowerShell window and don't close that window, or
- Use [NSSM (Non-Sucking Service Manager)](https://nssm.cc/) to install it as a Windows service.

For the rest of this guide, commands assume Linux/macOS. If you're on Windows, replace `nano` with `notepad` (or any editor), use `python` instead of `python3` if needed, and skip the supervisor section in favor of one of the Windows alternatives above.

---

## Part 3: Install the bot

These steps assume you've SSH'd into your VPS (or you're sitting at your Linux/macOS desktop). They install the bot in a Python virtual environment so it doesn't interfere with the system Python.

### 3.1 — Pick an install location

A reasonable default is your home directory:

```bash
cd ~
```

### 3.2 — Get the code onto the machine

You have two options.

**Option A — Clone from a git repository.** If the bot is hosted on GitHub or another git host, clone it:

```bash
git clone https://github.com/YOUR-FORK/doma-volume-bot.git
cd doma-volume-bot
```

(Replace `YOUR-FORK` with the actual location of the repo you trust. If you obtained the bot directly from the Doma team or a friend, use the URL they gave you.)

**Option B — Copy the files manually.** If you received the bot as a folder or zip archive, copy it to the VPS using `scp`:

```bash
# From your laptop:
scp -r ./doma-volume-bot root@YOUR.VPS.IP.ADDRESS:~/
```

Then on the VPS:

```bash
cd ~/doma-volume-bot
```

Either way, after this step you should be inside the `doma-volume-bot` directory and `ls` should show:

```
README.md
config.py
requirements.txt
shared.py
state.py
swap_executor.py
volume_bot.py
volume_bot.supervisor.conf.example
.env.example
```

If any of those are missing, stop and verify your copy is complete before continuing.

### 3.3 — Create a Python virtual environment

This isolates the bot's Python dependencies from anything else on the system:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

You should now see `(.venv)` at the start of your prompt. From now on, every Python command you run for the bot should be prefixed by activating this venv. If you reconnect via SSH later, run `source .venv/bin/activate` again before running the bot.

### 3.4 — Install Python dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

This installs `web3`, `eth-account`, and `python-dotenv`. Expect the install to take 30–90 seconds and produce a few lines of output ending with `Successfully installed ...`. If you see errors, the most common causes are:

- **Old Python.** Run `python3 --version` and confirm it's 3.10 or newer.
- **Missing system libraries.** On Debian/Ubuntu, run `apt install -y python3-dev build-essential libssl-dev libffi-dev`, then re-run the pip install.

### 3.5 — Verify the installation

```bash
python3 -c "import web3; import eth_account; import dotenv; print('OK')"
```

You should see `OK`. If you get an `ImportError`, the venv isn't active, or the install failed silently. Re-activate the venv (`source .venv/bin/activate`) and re-run the install command.

---

## Part 4: Find your pool info on doma.xyz

The bot needs four things from your token's pool page:

| What you need | Why |
|---|---|
| **Token address** | Tells the bot which token you're trading against USDC.e. |
| **Pool address** | The bot reads price and TVL directly from this contract. |
| **Pool fee tier** | Determines per-swap cost. Wrong value = swap reverts. |
| **Token decimals** | Used to convert USD amounts to token amounts. Wrong value = swap fails. |

### 4.1 — Open the pool page

1. In your browser, go to [https://doma.xyz/explore](https://doma.xyz/explore).
2. Find your domain token. You can search by name, ticker, or scroll the leaderboard.
3. Click into your token's detail page. You should see a chart, holders, and a list of pools.
4. Click into the **V3 pool** (it will usually be paired with USDC.e). If your token has multiple pools, the V3 pool you want is the one you intend to generate volume on — typically the one with the most liquidity.

### 4.2 — Copy the pool address

On the pool page, you'll see a long `0x...` address labeled as the pool contract. Click the copy icon next to it (or click the address itself — most explorers select-and-copy on click). The address is 42 characters long, starting with `0x`, e.g.:

```
0x1234567890abcdef1234567890abcdef12345678
```

Save it in a notepad alongside a label like `POOL_ADDRESS:` so you don't lose it.

### 4.3 — Copy the token address (the non-USDC.e side)

The pool page will show the two tokens in the pool — your domain token and USDC.e. **Copy the address of your domain token, not USDC.e.** USDC.e on Doma is always `0x31EEf89D5215C305304a2fA5376a1f1b6C5dc477`; the bot already has this baked in.

Save it as `TOKEN_ADDRESS:`.

### 4.4 — Note the pool fee tier

The fee tier is shown as a percentage on the pool page — you'll see one of:

- 0.01%
- 0.05% (most Doma launchpad tokens)
- 0.30%
- 1.00%

The bot's `POOL_FEE` setting is in **Uniswap V3 hundredths-of-basis-point units**, which means you multiply the percentage by 10,000:

| Displayed fee | `POOL_FEE` value |
|---|---|
| 0.01% | `100` |
| 0.05% | `500` |
| 0.30% | `3000` |
| 1.00% | `10000` |

Save the correct number for your pool — guessing wrong here will make every swap revert.

### 4.5 — Note the token decimals

This one is easy to overlook. Most Doma launchpad tokens use **6 decimals** (like USDC.e). If your token is something exotic — for example, an ETH/WETH wrapper — it may use 18 decimals.

If you're unsure:

- On the token page on doma.xyz, look for "decimals" in the contract details.
- Or, paste the token address into a Doma block explorer and look at the `decimals()` view function on the ERC-20 contract.

For the vast majority of Doma launchpad tokens, the answer is `6`. If you're not sure, **ask in your community Discord before guessing**. A wrong decimals value will cause the bot to send obscenely large or obscenely small token amounts and either fail loudly or — worst case — make a tiny but real economic mistake.

You should now have written down somewhere:

```
POOL_ADDRESS:    0x...
TOKEN_ADDRESS:   0x...
POOL_FEE:        500       (or whatever matches your pool)
TOKEN_DECIMALS:  6         (or 18 for ETH/WETH-style tokens)
```

---

## Part 5: Configure the bot

The bot is configured via a `.env` file in the project directory. The repo includes a template called `.env.example`. Copy it to `.env` and fill it in.

### 5.1 — Copy the template

```bash
cp .env.example .env
```

### 5.2 — Open the .env in an editor

```bash
nano .env
```

(If you prefer `vim` or another editor, use that. On Windows, open it in Notepad or VS Code.)

### 5.3 — Walk through every required field

The template is organized into sections. Here's what to fill in:

#### Wallet section

```
MNEMONIC=
MNEMONIC_ACCOUNT_INDEX=0
PRIVATE_KEY=
```

Fill in **either** `MNEMONIC` (the 12 or 24 word seed phrase from Part 1) **or** `PRIVATE_KEY` — not both. The mnemonic is recommended because it lets you recover the wallet anywhere with a standard wallet app.

If using `MNEMONIC`:

```
MNEMONIC=word1 word2 word3 word4 word5 word6 word7 word8 word9 word10 word11 word12
MNEMONIC_ACCOUNT_INDEX=0
```

The mnemonic should be one line, with a single space between each word, no leading or trailing whitespace, no quotes. `MNEMONIC_ACCOUNT_INDEX=0` means use the first account derived from the seed (`m/44'/60'/0'/0/0`) — the same address most wallets show by default. Only change this if you specifically generated multiple accounts from the same mnemonic and want to use a different one.

If using `PRIVATE_KEY` instead:

```
PRIVATE_KEY=0xabcdef1234...
```

The leading `0x` is optional — the bot will add it if missing. The key should be 64 hex characters (66 with the `0x` prefix).

⚠️ **Triple-check that the wallet you put here is the dedicated one you generated in Part 1, not your main wallet.** If you're not 100% sure, stop and re-do Part 1.

#### Network section

```
RPC_URL=https://doma.drpc.org
RPC_BACKUP=https://rpc.doma.xyz
CHAIN_ID=97477
```

The defaults are correct for Doma mainnet. Leave them as-is unless you have a private RPC endpoint you'd prefer to use for higher rate limits or lower latency.

#### Doma V3 contracts section

```
USDCE_ADDRESS=0x31EEf89D5215C305304a2fA5376a1f1b6C5dc477
UNIVERSAL_ROUTER=0x5089863E97196773038f98459262D866f2281f58
```

These are protocol-level addresses — the same for every Doma launchpad token. **Leave these alone.**

#### Your domain token section

```
TOKEN_ADDRESS=
TOKEN_SYMBOL=YOURTOKEN
POOL_ADDRESS=
POOL_FEE=500
TOKEN_DECIMALS=6
USDCE_DECIMALS=6
```

Fill in:

- `TOKEN_ADDRESS` — the address you copied in Part 4.3
- `TOKEN_SYMBOL` — your token's ticker (used only for log readability)
- `POOL_ADDRESS` — the address you copied in Part 4.2
- `POOL_FEE` — the value from the table in Part 4.4
- `TOKEN_DECIMALS` — almost always `6`, occasionally `18` (Part 4.5)
- `USDCE_DECIMALS` — leave as `6`

#### Volume strategy section (the tunable knobs)

```
SWAP_SIZE_USD_MIN=5
SWAP_SIZE_USD_MAX=25
SWAP_INTERVAL_SEC_MIN=60
SWAP_INTERVAL_SEC_MAX=300
MAX_SLIPPAGE_PCT=0.005
```

These defaults produce a swap somewhere between $5 and $25 in size every 1–5 minutes. Over 24 hours that's roughly 290–1440 swaps, generating between ~$1500 and ~$36,000 in raw volume per day. The actual number depends entirely on how the random ranges play out and how often safety checks block a swap.

For your **first run**, keep the defaults. Tune them after you have a feel for what's happening (covered in Part 10).

The slippage tolerance of `0.005` (0.5%) is reasonable for most pools. Lower values reduce your loss per swap but cause more swaps to abort when the price has moved between estimation and execution. Higher values trade fewer aborts for slightly worse fills.

#### Safety guards section

```
DAILY_LOSS_BUDGET_USD=5
MIN_POOL_TVL_USD=5000
MAX_SWAP_PCT_OF_TVL=0.005
MAX_SWAP_IMPACT_BPS=50
```

- `DAILY_LOSS_BUDGET_USD=5` — the bot will halt for the day after losing $5 in fees + slippage. At a 0.05% pool, that's ~$5,000 of round-trip volume. Increase this only after you've watched the bot for a few days and understand how fast it accumulates cost.
- `MIN_POOL_TVL_USD=5000` — the bot won't swap if the pool has less than $5k of total liquidity. If your pool is smaller, lower this — but understand that very thin pools have high slippage even on tiny swaps.
- `MAX_SWAP_PCT_OF_TVL=0.005` — no single swap can be larger than 0.5% of pool TVL. Default is safe; only loosen it if you genuinely need bigger swaps and accept the price impact.
- `MAX_SWAP_IMPACT_BPS=50` — skip any swap whose estimated price impact exceeds 0.5% (50 basis points). This is a belt-and-suspenders check on top of `MAX_SWAP_PCT_OF_TVL`.

#### Mode section

```
DRY_RUN=true
LOG_LEVEL=INFO
```

**Leave `DRY_RUN=true` for your first run.** Dry-run mode prints what the bot would do but never sends a transaction. You'll switch this to `false` in Part 8.

`LOG_LEVEL=INFO` is a standard Python log level. The bot's logging is simple — leaving this as `INFO` is fine.

### 5.4 — Save and close

In `nano`, press `Ctrl+O` then `Enter` to save, then `Ctrl+X` to exit.

### 5.5 — Lock down file permissions

The `.env` file now contains your wallet's private key or mnemonic. Restrict it so no other user on the machine can read it:

```bash
chmod 600 .env
```

This makes the file readable and writable only by your user. On a VPS where you're the only user, this is a no-op in practice, but it's a good habit.

### 5.6 — Verify the .env was loaded correctly

The bot's `config.py` will refuse to start if required fields are missing. You can do a quick syntax check now:

```bash
python3 -c "import config; print('Config loaded OK'); print('Wallet token addr:', config.TOKEN_ADDRESS); print('Pool addr:', config.POOL_ADDRESS); print('Pool fee:', config.POOL_FEE)"
```

If everything is filled in, you'll see something like:

```
Config loaded OK
Wallet token addr: 0xAbCd...1234
Pool addr: 0xDeF0...5678
Pool fee: 500
```

If you see `ValueError: TOKEN_ADDRESS not set in .env`, you forgot to fill in `TOKEN_ADDRESS`. Same for `POOL_ADDRESS`. If you see `ValueError: Set either MNEMONIC or PRIVATE_KEY in your .env file`, neither wallet field was filled in.

---

## Part 6: Fund the wallet

Now that the bot knows which wallet it's using, you need to send funds to that wallet's address on Doma chain. The wallet needs three things:

| Asset | Recommended starting amount | Purpose |
|---|---|---|
| **USDC.e** on Doma | $50–$200 | Inventory for "buy" swaps. |
| **Your domain token** on Doma | $50–$200 worth | Inventory for "sell" swaps. |
| **ETH** on Doma | ~0.001 ETH (~$3 at typical prices) | Pays gas for thousands of transactions. |

### 6.1 — Get the wallet address

You need the Ethereum address derived from the mnemonic you put in `.env`. The easiest way to confirm it:

```bash
python3 -c "from shared import load_wallet; print('Wallet address:', load_wallet()[0])"
```

This prints the address the bot will use. **Triple-check this matches the address you wrote down in Part 1.** If it doesn't, the mnemonic in `.env` is wrong, or `MNEMONIC_ACCOUNT_INDEX` is set to a value other than 0.

Copy that address — call it `BOT_ADDRESS` for the rest of this guide.

### 6.2 — Send ETH for gas

You need ETH on **Doma chain**, not on Ethereum mainnet or any other L2. You have several routes:

- **Bridge from another EVM chain.** Use the bridge linked from doma.xyz (or whatever bridge is recommended in Doma's docs at the time you're reading this). You'll need ~0.001 ETH on the destination chain.
- **Withdraw directly from a CEX that supports Doma chain.** If your exchange lists ETH withdrawals to Doma, this is the simplest path.
- **Send from another wallet you control on Doma.** If you already have ETH on Doma in your main wallet, send a small amount to `BOT_ADDRESS`.

Send to `BOT_ADDRESS`. Wait for the transaction to confirm. Then verify:

```bash
python3 -c "
from shared import connect, load_wallet
w3 = connect()
addr = load_wallet()[0]
bal = w3.eth.get_balance(addr) / 10**18
print(f'ETH balance: {bal:.6f} ETH')
"
```

You should see something like `ETH balance: 0.001000 ETH`. If you see `0.000000`, the funds haven't arrived yet — wait another minute and try again.

### 6.3 — Send USDC.e

USDC.e on Doma is the bridged USDC contract at `0x31EEf89D5215C305304a2fA5376a1f1b6C5dc477`. You can:

- Bridge USDC from another chain via the Doma-recommended bridge.
- Withdraw from a CEX that supports USDC on Doma chain (check your exchange's list).
- Send from your main wallet on Doma if you already hold USDC.e there.

Send $50–$200 worth (50,000,000–200,000,000 in raw units, since USDC.e has 6 decimals — but you'll just type "50" or whatever in your wallet's UI). Verify the balance:

```bash
python3 -c "
from web3 import Web3
from shared import connect, load_wallet, ERC20_ABI
import config
w3 = connect()
addr = load_wallet()[0]
c = w3.eth.contract(address=Web3.to_checksum_address(config.USDCE_ADDRESS), abi=ERC20_ABI)
bal = c.functions.balanceOf(addr).call() / 10**config.USDCE_DECIMALS
print(f'USDC.e balance: {bal:.4f}')
"
```

### 6.4 — Send your domain token

Send roughly the same USD value of your domain token as you sent in USDC.e. The bot alternates buys and sells, so it needs inventory of both sides. If you only fund one side, the bot will be able to do the first few swaps in one direction and then start failing with "insufficient balance" errors when it tries the other direction.

How to acquire your domain token depends on whether you already hold it:

- **You're the project founder / treasury holder.** Send the appropriate amount from your project wallet.
- **You're a community member with no holdings yet.** Buy the token from the V3 pool yourself first. Use a Doma-native UI (linked from doma.xyz) or a DEX aggregator that supports Doma chain.

Verify the balance:

```bash
python3 -c "
from web3 import Web3
from shared import connect, load_wallet, ERC20_ABI
import config
w3 = connect()
addr = load_wallet()[0]
c = w3.eth.contract(address=Web3.to_checksum_address(config.TOKEN_ADDRESS), abi=ERC20_ABI)
bal = c.functions.balanceOf(addr).call() / 10**config.TOKEN_DECIMALS
print(f'{config.TOKEN_SYMBOL} balance: {bal:.4f}')
"
```

### 6.5 — Sanity check: do the dollar values roughly match?

The bot picks a random USD swap size each cycle. If your USDC.e balance is $50 and your token balance is only worth $3, the first three swaps will work and the fourth will hit an "insufficient token balance" warning, then the bot will skip and retry. It'll eventually rebalance itself when the alternating direction lets it sell off accumulated tokens, but this is a wasted cycle.

A good rule of thumb: fund roughly equal USD value on both sides. Round numbers are fine — $100 of each is a perfectly reasonable starting point.

---

## Part 7: Dry run (no real transactions)

Before risking real money, you'll run the bot in dry-run mode. In dry-run, the bot does everything except actually send transactions: it connects to the RPC, reads the pool state, picks a random swap size and direction, runs all safety checks, and prints what it would do. **No funds move.**

### 7.1 — Verify DRY_RUN is true

In your `.env` file, confirm:

```
DRY_RUN=true
```

You can also force dry-run from the command line by passing `--dry-run`, regardless of what's in `.env`:

```bash
python3 volume_bot.py --dry-run
```

### 7.2 — Run it

Start the bot:

```bash
python3 volume_bot.py
```

(Or `python3 volume_bot.py --dry-run` to be extra-explicit.)

### 7.3 — What you should see

The first thing the bot prints is a header like:

```
2026-05-13 12:34:56  INFO  ======================================================================
2026-05-13 12:34:56  INFO    Doma Volume Bot — YOURTOKEN
2026-05-13 12:34:56  INFO  ======================================================================
2026-05-13 12:34:56  INFO    Pool:         0xDeF0...5678
2026-05-13 12:34:56  INFO    Fee tier:     0.050%
2026-05-13 12:34:56  INFO    Swap size:    $5.0-25.0
2026-05-13 12:34:56  INFO    Interval:     60-300s
2026-05-13 12:34:56  INFO    Daily budget: $5.0
2026-05-13 12:34:56  INFO    DRY RUN:      True
2026-05-13 12:34:57  INFO  Connected to RPC: chain_id=97477
2026-05-13 12:34:57  INFO    Wallet:       0xAbCd...1234
```

Verify carefully:

- The pool address matches what you put in `.env`.
- The fee tier matches your pool (0.050% for `POOL_FEE=500`, etc.).
- The wallet address matches the address you funded.
- `DRY RUN: True` — confirms no real transactions will be sent.

Within a few seconds you'll see a swap cycle begin:

```
2026-05-13 12:34:58  INFO  [#1] direction=buy  size=$12.34  price=$0.001234  tvl=$15234  daily=$0.00vol/$0.0000cost
2026-05-13 12:34:58  INFO    [DRY RUN] buy: 12340000 (in) → expect 9999987654 (out)
2026-05-13 12:34:58  INFO    sleeping 187s...
```

What this tells you:

- The bot picked a $12.34 swap size from the random range.
- It read the pool price as $0.001234 per token.
- The pool's TVL is ~$15,234.
- No real swap was sent; the bot would have sent 12,340,000 raw units (= $12.34 of USDC.e) and expected 9,999,987,654 raw units of your token in return.
- It will sleep 187 seconds before the next cycle.

If you see this pattern, **everything is working**. Let it run for a few cycles to confirm the alternation works (next cycle should be `direction=sell`, then `buy`, etc.).

### 7.4 — Common dry-run errors

- **`ValueError: TOKEN_ADDRESS not set in .env`** — you forgot to fill `TOKEN_ADDRESS`. Edit `.env` and try again.
- **`ValueError: POOL_ADDRESS not set in .env`** — same, but for `POOL_ADDRESS`.
- **`Could not connect to any RPC`** — neither RPC URL responded. Check your VPS has internet (`curl https://doma.drpc.org`). If you see an SSL or timeout error, your VPS may be in a region with poor connectivity to the RPC; consider using a different RPC URL.
- **`Bad pool price, retrying in 30s`** — the pool returned a `sqrt_price_x96` of 0, which means the pool exists but has never been initialized or has zero liquidity. Verify you're pointing at the correct V3 pool and not, for example, an inactive or wrong-fee-tier pool with the same token pair.
- **`safety check failed: Pool TVL $X < minimum $5000`** — your pool is smaller than `MIN_POOL_TVL_USD`. Either lower `MIN_POOL_TVL_USD` in `.env` (and accept the higher slippage that comes with thin pools), or wait until the pool has more liquidity.
- **`safety check failed: Swap $X > 0.5% of pool ($Y)`** — your random swap size was too big for the pool. Either reduce `SWAP_SIZE_USD_MAX` or raise `MAX_SWAP_PCT_OF_TVL`. Default ranges should be fine for a $5k+ TVL pool.

### 7.5 — Stop the dry run

When you're satisfied, press `Ctrl+C`. You should see:

```
^C
Stopped by user.
```

The bot exits cleanly. Nothing was spent, no transactions were sent.

---

## Part 8: First live test — one cycle

Now you'll do one real swap. Just one. You'll watch it carefully, verify the result on-chain, and only then graduate to continuous running.

### 8.1 — Switch DRY_RUN to false

Edit `.env`:

```bash
nano .env
```

Change:

```
DRY_RUN=true
```

to:

```
DRY_RUN=false
```

Save and exit (`Ctrl+O`, `Enter`, `Ctrl+X`).

### 8.2 — Run the bot

```bash
python3 volume_bot.py
```

This time `DRY RUN: False` should appear in the header. The bot will then start its first cycle.

### 8.3 — Watch the first swap

The first time the bot ever runs against a token, it needs to do **two one-time approvals** before the actual swap can happen:

```
2026-05-13 12:40:00  INFO  [#1] direction=buy  size=$11.20 ...
2026-05-13 12:40:01  INFO    Approving 0x31EEf89D... → Permit2 (one-time)
2026-05-13 12:40:01  INFO    ERC20→Permit2 tx: 0x...
2026-05-13 12:40:05  INFO    ERC20→Permit2 ✓ block 12345
2026-05-13 12:40:05  INFO    Approving Permit2 0x31EEf89D... → Router (one-time)
2026-05-13 12:40:06  INFO    Permit2→Router tx: 0x...
2026-05-13 12:40:10  INFO    Permit2→Router ✓ block 12346
2026-05-13 12:40:11  INFO    swap tx: 0x...
2026-05-13 12:40:15  INFO    swap ✓ block 12347
2026-05-13 12:40:15  INFO    swap ✓ received 9876543210 (raw)
2026-05-13 12:40:15  INFO    swap ✓ buy: in=$11.2000 out=$11.1944 cost=$0.0056
2026-05-13 12:40:15  INFO    sleeping 142s...
```

What just happened:

1. **Approval 1**: Your USDC.e was approved to be pulled by the canonical Permit2 contract (`0x000000000022D473030F116dDEE9F6B43aC78BA3`). This is a one-time setup per token; it persists forever.
2. **Approval 2**: Permit2 was authorized to grant the Universal Router permission to spend your USDC.e. Also one-time per token, with a far-future expiration (year 2100).
3. **The swap**: The Universal Router executed a V3 exact-input swap, taking your $11.20 of USDC.e and returning ~$11.19 of your token.

The cost ($0.0056) is the pool fee for this $11.20 swap (0.05% of $11.20 = $0.0056), which matches your `POOL_FEE=500` setting. ✓

### 8.4 — Verify on-chain

Open the swap transaction in a Doma block explorer. Take the `0x...` hash from the `swap tx:` line and paste it into the explorer's search. You should see:

- `From`: your bot wallet address
- `To`: the Universal Router (`0x5089863E97196773038f98459262D866f2281f58`)
- One token transferred out of your wallet (USDC.e, in this example) and one transferred in (your token)
- Status: **Success**

If the explorer says **Failed**, see the troubleshooting section at the end of this guide.

### 8.5 — Stop after the first swap

Press `Ctrl+C` after the first successful swap. Verify with the on-chain explorer that everything looks correct. Check your wallet balance:

```bash
python3 -c "
from web3 import Web3
from shared import connect, load_wallet, ERC20_ABI
import config
w3 = connect()
addr = load_wallet()[0]
usdce = w3.eth.contract(address=Web3.to_checksum_address(config.USDCE_ADDRESS), abi=ERC20_ABI)
token = w3.eth.contract(address=Web3.to_checksum_address(config.TOKEN_ADDRESS), abi=ERC20_ABI)
print(f'USDC.e: {usdce.functions.balanceOf(addr).call()/10**config.USDCE_DECIMALS:.4f}')
print(f'{config.TOKEN_SYMBOL}: {token.functions.balanceOf(addr).call()/10**config.TOKEN_DECIMALS:.4f}')
print(f'ETH: {w3.eth.get_balance(addr)/10**18:.6f}')
"
```

Compare against what you funded. The USDC.e should have decreased by ~$11.20, the token balance should have increased by approximately the same dollar value, and ETH should be slightly lower (gas).

If any of those don't match, **stop and investigate before running the bot continuously.**

### 8.6 — Optional: let it run for a few more cycles

If the first swap looked clean, you can let the bot run for 5–10 minutes to confirm the alternating behavior:

```bash
python3 volume_bot.py
```

The next swap should be `direction=sell` (selling your token back to USDC.e). After that, `direction=buy` again, and so on.

When you're confident, `Ctrl+C` to stop.

---

## Part 9: Run continuously with supervisor

Up to this point, you've been running the bot in the foreground — the moment you close your SSH session, the bot stops. For continuous operation, you need a process supervisor that:

- Starts the bot automatically on boot.
- Restarts it if it crashes.
- Captures its logs to disk.
- Lets you start/stop/check status with simple commands.

The repo includes a ready-made [supervisord](http://supervisord.org/) config you'll customize and install.

### 9.1 — Install supervisor (if not already done)

On Debian/Ubuntu:

```bash
sudo apt install -y supervisor
```

On other Linux distros, install the equivalent package. On macOS, `brew install supervisor` works but is rarely the right tool — for macOS, prefer `launchd` (out of scope for this guide). On Windows, prefer NSSM or Task Scheduler.

### 9.2 — Look at the example config

The repo contains `volume_bot.supervisor.conf.example`:

```ini
[program:volume_bot]
command=/path/to/your/venv/bin/python3 /path/to/doma-volume-bot/volume_bot.py
directory=/path/to/doma-volume-bot
autostart=true
autorestart=true
startsecs=5
startretries=3
stopwaitsecs=10
stopasgroup=true
killasgroup=true
user=root
stdout_logfile=/var/log/supervisor/volume_bot.out.log
stderr_logfile=/var/log/supervisor/volume_bot.err.log
stdout_logfile_maxbytes=10MB
stdout_logfile_backups=3
stderr_logfile_maxbytes=10MB
stderr_logfile_backups=3
environment=PYTHONUNBUFFERED="1"
```

You need to edit two paths and (optionally) the user.

### 9.3 — Determine your real paths

Find the absolute path to your venv's Python and your bot directory:

```bash
which python3
# (after activating .venv) → /home/youruser/doma-volume-bot/.venv/bin/python3

pwd
# /home/youruser/doma-volume-bot
```

Note these two paths.

### 9.4 — Create the supervisor config

Copy and edit:

```bash
sudo cp volume_bot.supervisor.conf.example /etc/supervisor/conf.d/volume_bot.conf
sudo nano /etc/supervisor/conf.d/volume_bot.conf
```

Replace the two `/path/to/...` lines with your real paths. Example:

```ini
command=/home/youruser/doma-volume-bot/.venv/bin/python3 /home/youruser/doma-volume-bot/volume_bot.py
directory=/home/youruser/doma-volume-bot
```

If you're not running as root (you shouldn't on a multi-user system), change:

```ini
user=root
```

to:

```ini
user=youruser
```

Save and exit.

### 9.5 — Tell supervisor about the new config

```bash
sudo supervisorctl reread
sudo supervisorctl update
```

`reread` makes supervisor scan its config directory and notice the new file. `update` actually loads any new programs. You should see something like:

```
volume_bot: added process group
```

### 9.6 — Start the bot

```bash
sudo supervisorctl start volume_bot
```

Expected output:

```
volume_bot: started
```

### 9.7 — Verify it's running

```bash
sudo supervisorctl status volume_bot
```

You should see:

```
volume_bot                       RUNNING   pid 12345, uptime 0:00:08
```

If you see `FATAL` or `STOPPED`, check the error log:

```bash
sudo tail -n 100 /var/log/supervisor/volume_bot.err.log
```

The most common causes of immediate failure are:

- Wrong path to `python3` in the supervisor config.
- Wrong `directory=` (so `.env` can't be loaded).
- Permissions error reading `.env` (you set `chmod 600` as the wrong user).

### 9.8 — Tail the logs in real time

```bash
sudo tail -f /var/log/supervisor/volume_bot.out.log
```

You should see the same log output as when you ran the bot manually, including swap cycles, sleeps, and balances. Press `Ctrl+C` to stop tailing (this does **not** stop the bot — it just stops your live log view).

### 9.9 — Useful supervisor commands

```bash
# Check status
sudo supervisorctl status

# Stop the bot (graceful — finishes the current swap cycle's sleep, then exits)
sudo supervisorctl stop volume_bot

# Start the bot
sudo supervisorctl start volume_bot

# Restart the bot (e.g., after editing .env)
sudo supervisorctl restart volume_bot

# Tail combined output
sudo supervisorctl tail -f volume_bot

# Tail just stderr
sudo supervisorctl tail -f volume_bot stderr
```

---

## Part 10: Monitor and tune

The bot is running. Now you watch it for a few days, then tune.

### 10.1 — Check daily totals from the SQLite database

The bot logs every swap into a SQLite file called `volume_bot.db` in the bot's directory. To see today's totals:

```bash
sqlite3 ~/doma-volume-bot/volume_bot.db "SELECT * FROM daily_totals ORDER BY date DESC LIMIT 7;"
```

You'll get something like:

```
date        swaps_count  volume_usd  cost_usd
2026-05-13  87           1043.21     1.0432
2026-05-12  142          1722.80     1.7228
2026-05-11  108          1287.45     1.2874
```

Three columns:

- `swaps_count` — number of successful swaps that day
- `volume_usd` — total dollar value swapped (one direction at a time, so two swaps of $10 each = $20 here)
- `cost_usd` — total fees + slippage paid that day

Compare `cost_usd` against your `DAILY_LOSS_BUDGET_USD` to see how close you're getting to the daily cap.

### 10.2 — Inspect individual swaps

```bash
sqlite3 ~/doma-volume-bot/volume_bot.db "SELECT executed_at, direction, amount_in_usd, amount_out_usd, cost_usd, status FROM swaps ORDER BY id DESC LIMIT 10;"
```

This shows the most recent 10 swaps with direction, dollar amounts, cost, and status. Anything other than `OK` in the status column is worth investigating in the log file.

### 10.3 — Read the log file

```bash
sudo tail -n 500 /var/log/supervisor/volume_bot.out.log
```

For continuous viewing:

```bash
sudo tail -f /var/log/supervisor/volume_bot.out.log
```

What "healthy" looks like:

- A new `[#N] direction=...` line every 1–5 minutes.
- Each `swap ✓` line shows `cost=$0.0XXX` matching your fee tier.
- `daily=$X.XXvol/$Y.YYYYcost` increases steadily over the day.
- No repeated errors.

What "unhealthy" looks like:

- Repeated `safety check failed: Pool TVL ...` — pool may have lost liquidity.
- Repeated `insufficient ... balance` — your wallet ran low on one side; the bot can't proceed in that direction.
- Repeated `swap failed` — could be slippage too tight, RPC issues, or pool state changed.
- `Daily loss exceeded budget` — bot has halted for the day; this is **expected** and self-resolving (it'll resume tomorrow). If you're surprised by it, your `DAILY_LOSS_BUDGET_USD` is too tight relative to your swap activity.

### 10.4 — Tuning the swap size

If you want **more volume per day**, the simplest knob is to increase `SWAP_SIZE_USD_MAX`:

```
SWAP_SIZE_USD_MIN=10
SWAP_SIZE_USD_MAX=50
```

Then restart the bot:

```bash
sudo supervisorctl restart volume_bot
```

Be aware: bigger swaps mean bigger per-swap cost, so you'll hit `DAILY_LOSS_BUDGET_USD` sooner unless you raise it as well.

### 10.5 — Tuning the interval

If you want more swaps per day (which means more volume but also faster cost accumulation), tighten the interval range:

```
SWAP_INTERVAL_SEC_MIN=30
SWAP_INTERVAL_SEC_MAX=120
```

⚠️ Don't go below 30 seconds — at very tight intervals the activity starts to look mechanical and may be detectable as bot activity. The default range (60–300 seconds) is a good middle ground.

### 10.6 — Tuning the daily budget

After a few days you'll have a sense of how much the bot costs you per dollar of volume. To set `DAILY_LOSS_BUDGET_USD` correctly, decide what daily volume target you actually want, then:

```
DAILY_LOSS_BUDGET_USD ≈ (target daily volume) × (pool fee) × 2
```

For example, $5,000/day volume on a 0.05% pool:

```
$5000 × 0.0005 × 2 = $5.00
```

…which is exactly the default. For $20,000/day, you'd want a $20 daily budget. Don't set the budget far above what you actually intend to spend; the budget is a safety cap, not a target.

### 10.7 — Refilling the wallet

Eventually one or both sides of the wallet will drift. The alternating buy/sell pattern is roughly balanced, but the bot picks **random sizes** each cycle, so over time you can accumulate a small surplus on one side. When the bot starts logging `insufficient balance` more often than every few cycles, top up the lower side.

To check current balances at any time:

```bash
cd ~/doma-volume-bot
source .venv/bin/activate
python3 -c "
from web3 import Web3
from shared import connect, load_wallet, ERC20_ABI
import config
w3 = connect()
addr = load_wallet()[0]
usdce = w3.eth.contract(address=Web3.to_checksum_address(config.USDCE_ADDRESS), abi=ERC20_ABI)
token = w3.eth.contract(address=Web3.to_checksum_address(config.TOKEN_ADDRESS), abi=ERC20_ABI)
print(f'USDC.e: {usdce.functions.balanceOf(addr).call()/10**config.USDCE_DECIMALS:.4f}')
print(f'{config.TOKEN_SYMBOL}: {token.functions.balanceOf(addr).call()/10**config.TOKEN_DECIMALS:.4f}')
print(f'ETH: {w3.eth.get_balance(addr)/10**18:.6f}')
"
```

If ETH falls below ~0.0002, send more — running out of gas mid-swap will cause the swap to fail and the bot will retry.

### 10.8 — Rotating logs (housekeeping)

The supervisor config rotates logs at 10 MB and keeps 3 backups. Beyond that, old log files are deleted. The SQLite DB grows by a small amount per swap (a few hundred bytes per row). Even after months of operation the DB will be only a few MB, so you don't need to worry about it.

If you want to keep historical totals but truncate detailed swap logs:

```bash
sqlite3 ~/doma-volume-bot/volume_bot.db "DELETE FROM swaps WHERE executed_at < date('now', '-30 days');"
```

Run that monthly via cron if you care about disk space.

---

## Part 11: Stop the bot

You may want to stop the bot temporarily (to update config, rotate keys, or pause activity) or permanently.

### 11.1 — Stop temporarily

```bash
sudo supervisorctl stop volume_bot
```

The bot exits cleanly. No state is lost. To restart:

```bash
sudo supervisorctl start volume_bot
```

### 11.2 — Stop permanently and remove the supervisor config

```bash
sudo supervisorctl stop volume_bot
sudo rm /etc/supervisor/conf.d/volume_bot.conf
sudo supervisorctl reread
sudo supervisorctl update
```

The `reread` + `update` removes the now-orphan program from supervisor's tracking.

### 11.3 — Drain the wallet

If you're shutting down for good and want to recover the funds:

1. Stop the bot (above).
2. Open MetaMask (or your wallet of choice) and import the seed phrase from `.env` — temporarily, just to send funds out.
3. Send all USDC.e, your domain token, and ETH back to your main wallet.
4. **Remove the imported wallet from MetaMask immediately** (right-click the account → **Hide account**, or for hardware-wallet-style isolation, use the "remove account" flow). Do not leave the bot's seed phrase loaded in your main wallet app.
5. Delete the `.env` file from the VPS:

```bash
shred -u ~/doma-volume-bot/.env
```

(`shred -u` overwrites the file before deleting it. Plain `rm` works too but isn't as secure on traditional disks.)

### 11.4 — Emergency exit

If something is going very wrong (e.g., the bot is logging huge errors and you suspect funds at risk):

```bash
sudo supervisorctl stop volume_bot
```

Then immediately move funds out of the wallet using your wallet app. The most common way to "drain" the wallet quickly is to import the seed phrase into MetaMask, switch the network to Doma, and send each token to a safer address one at a time.

If you don't have access to your VPS at the moment (e.g., you're traveling and SSH is broken), the fact that you have the seed phrase backed up on paper means you can drain the wallet from any device with MetaMask, even if the bot is still running. The bot will eventually run out of inventory and start erroring on every cycle, but it can't move funds out of the wallet on its own — only swap them within the configured pool.

---

## Appendix A: Troubleshooting (problem → fix)

| Problem | Cause | Fix |
|---|---|---|
| `ValueError: Set either MNEMONIC or PRIVATE_KEY in your .env file` | Both wallet fields empty in `.env` | Edit `.env`, fill in `MNEMONIC` (preferred) or `PRIVATE_KEY` |
| `ValueError: TOKEN_ADDRESS not set in .env` | `TOKEN_ADDRESS` missing or still `0x0000...` | Edit `.env`, paste the token address from doma.xyz pool page |
| `ValueError: POOL_ADDRESS not set in .env` | `POOL_ADDRESS` missing or still `0x0000...` | Edit `.env`, paste the pool address from doma.xyz pool page |
| `ValueError: SWAP_SIZE_USD_MIN must be ≤ SWAP_SIZE_USD_MAX` | You set min higher than max | Fix the values so min ≤ max |
| `Could not connect to any RPC` | Network issue or wrong RPC URLs | Verify VPS internet (`curl https://doma.drpc.org`); check `RPC_URL` and `RPC_BACKUP` are correct |
| `Bad pool price, retrying in 30s` (repeating forever) | Pool exists but is uninitialized or has zero liquidity | Verify `POOL_ADDRESS` is the active V3 pool with USDC.e on the other side; pool may need initial liquidity added |
| `safety check failed: Pool TVL $X < minimum $5000` | Pool is below your minimum TVL | Lower `MIN_POOL_TVL_USD` in `.env` (and accept higher slippage) or wait for the pool to grow |
| `safety check failed: Swap $X > 0.5% of pool ($Y)` | Random swap size exceeded `MAX_SWAP_PCT_OF_TVL` for current TVL | Lower `SWAP_SIZE_USD_MAX` or raise `MAX_SWAP_PCT_OF_TVL` |
| `safety check failed: Daily loss $X >= budget $Y` | Bot hit daily cost cap | Expected behavior. Bot resumes the next calendar day (UTC). Raise budget if intentional. |
| `insufficient 0x... balance (X.XXXX < Y.YYYY)` | Wallet ran out of inventory on one side | Send more USDC.e or token to the wallet |
| `swap failed (status=0)` | On-chain revert — usually slippage exceeded or stale price | Single failures are normal; bot retries next cycle. Repeated failures = raise `MAX_SLIPPAGE_PCT` slightly (e.g., 0.005 → 0.008) |
| `swap exception: nonce too low` | RPC saw a newer nonce than the bot expected (race) | Self-recovers on the next cycle when the bot re-fetches the nonce. Ignore unless persistent. |
| `swap parsed 0 tokens received` | Transaction succeeded on-chain but no Transfer event matched | Rare; usually a token with non-standard transfer logic. Verify the pool fee tier and token decimals are correct. |
| `Approving 0x... → Permit2 (one-time)` appearing every cycle | Approval transaction is failing silently | Check the wallet has enough ETH for gas; check the bot isn't running with wrong wallet |
| Bot starts then immediately exits | Usually a config error before the main loop | Check `/var/log/supervisor/volume_bot.err.log` for the Python traceback |
| Supervisor says `FATAL` | Bot exited too fast 3 times in a row | Run the bot manually first (`python3 volume_bot.py`) to see the actual error |
| `Connected to RPC: chain_id=X expected 97477` | Wrong RPC URL pointing at a different chain | Restore default `RPC_URL=https://doma.drpc.org` |
| `swap ✓ received 0 (raw)` | Output was below the minimum acceptable (slippage) | Try raising `MAX_SLIPPAGE_PCT` or reducing swap size |
| `permission denied: .env` | Run as wrong user | Either `chmod 644 .env` (less secure) or change the supervisor `user=` to match the file's owner |

---

## Appendix B: Cost math walkthroughs

### Example 1 — Conservative starting setup (0.05% pool)

Config:

```
SWAP_SIZE_USD_MIN=5
SWAP_SIZE_USD_MAX=25
SWAP_INTERVAL_SEC_MIN=60
SWAP_INTERVAL_SEC_MAX=300
DAILY_LOSS_BUDGET_USD=5
```

Average swap size: **$15** (midpoint).
Average interval: **180 seconds** (midpoint, 3 minutes).
Swaps per day: 86,400 / 180 ≈ **480 swaps**.
Volume per day: 480 × $15 = **$7,200/day** raw volume.

Cost per swap at 0.05% pool: $15 × 0.0005 = **$0.0075** per swap.
Daily cost: 480 × $0.0075 = **$3.60/day**.

This stays comfortably under the $5/day budget. You'd see ~$7,200 of volume per day for ~$3.60 of cost.

### Example 2 — Aggressive setup (0.05% pool)

Config:

```
SWAP_SIZE_USD_MIN=20
SWAP_SIZE_USD_MAX=80
SWAP_INTERVAL_SEC_MIN=30
SWAP_INTERVAL_SEC_MAX=120
DAILY_LOSS_BUDGET_USD=30
```

Average swap size: **$50**. Average interval: **75 seconds**.
Swaps per day: 86,400 / 75 ≈ **1,150 swaps**.
Volume per day: 1,150 × $50 = **$57,500/day** raw volume.

Cost per swap: $50 × 0.0005 = **$0.025**.
Daily cost: 1,150 × $0.025 = **$28.75/day**, hits the $30 budget late in the day and halts.

You'd see ~$50k+ of volume per day for ~$30 of cost. The wallet needs proportionally more inventory — if you're swinging $80 at a time, you should fund both sides with several hundred dollars.

### Example 3 — Why 0.30% pools get expensive fast

Same config as Example 1, but pool is 0.30%:

Cost per swap: $15 × 0.003 = **$0.045** (6× more than Example 1).
Daily cost: 480 × $0.045 = **$21.60/day** — 4× the budget.

Bot would halt after about 110 swaps (~$1,650 of volume), then sit idle for the rest of the day. To get the same daily volume as Example 1 on a 0.30% pool, you'd need a $25/day budget. **0.30% pools are 6× more expensive per dollar of volume than 0.05% pools.** If you have a choice of which pool to use, 0.05% is much cheaper.

### Example 4 — Sizing your wallet

Rule of thumb: fund each side with at least **5–10× your `SWAP_SIZE_USD_MAX`**. This gives the bot enough buffer that an occasional run of 4 buys in a row before the next sell doesn't drain one side.

For Example 1 above (`SWAP_SIZE_USD_MAX=25`):

- USDC.e: $125–$250
- Token: $125–$250 worth
- ETH for gas: 0.001 ETH (~$3 at typical prices, lasts thousands of swaps)

For Example 2 above (`SWAP_SIZE_USD_MAX=80`):

- USDC.e: $400–$800
- Token: $400–$800 worth
- ETH for gas: 0.002 ETH (more swaps per day = more gas)

Don't over-fund — if the host is compromised, every dollar you've put in is at risk. Keep the wallet right-sized for ~1–2 weeks of operation, then top up periodically.

---

## Appendix C: Security checklist

Run through this before going live and again every couple of months.

- [ ] **Bot wallet seed phrase is brand new** — never used in any other application, exchange, or wallet.
- [ ] **Seed phrase is written on paper** and stored somewhere safe (fireproof box, safety deposit box, etc.). Not in cloud storage. Not screenshotted.
- [ ] **`.env` file permissions are `600`** (`chmod 600 .env`).
- [ ] **`.env` is `.gitignore`d** — verify with `cat .gitignore` (the repo's stock `.gitignore` includes `.env` already).
- [ ] **Bot wallet holds only what's needed** — the absolute USD value in the wallet should be ~1–2 weeks of expected operation, never your treasury.
- [ ] **VPS has a non-root user** with sudo privileges; root SSH login is disabled.
- [ ] **VPS firewall** allows only SSH (port 22) inbound. The bot makes outbound connections only.
- [ ] **SSH access is via key, not password** — no `PasswordAuthentication yes` in `/etc/ssh/sshd_config`.
- [ ] **System is patched** — `sudo apt update && sudo apt upgrade -y` runs at least monthly (or auto-updates are enabled).
- [ ] **You know how to drain the wallet** without SSH access (i.e., you have the seed phrase and a wallet app that supports Doma chain).
- [ ] **You are not LPing the same pool** the bot is trading on, or you've consciously decided to accept the LP-vs-bot fee churn.
- [ ] **You've told your community** if you have any concerns about being seen as opaque about volume sources. Transparency beats getting caught.

---

## Appendix D: A quick reference of every config field

| Field | Required? | Default | Notes |
|---|---|---|---|
| `MNEMONIC` | One of MNEMONIC/PRIVATE_KEY | — | 12 or 24 word BIP-39 phrase. NEVER reuse main wallet. |
| `MNEMONIC_ACCOUNT_INDEX` | No | `0` | BIP-44 account index. Leave at 0 unless you know why. |
| `PRIVATE_KEY` | One of MNEMONIC/PRIVATE_KEY | — | Raw hex. With or without `0x` prefix. |
| `RPC_URL` | No | `https://doma.drpc.org` | Primary Doma RPC. |
| `RPC_BACKUP` | No | `https://rpc.doma.xyz` | Tried if primary fails. |
| `CHAIN_ID` | No | `97477` | Doma mainnet. Don't change. |
| `USDCE_ADDRESS` | No | `0x31EEf89D5215C305304a2fA5376a1f1b6C5dc477` | USDC.e on Doma. Don't change. |
| `UNIVERSAL_ROUTER` | No | `0x5089863E97196773038f98459262D866f2281f58` | Doma Universal Router. Don't change. |
| `TOKEN_ADDRESS` | **Yes** | — | Your domain token's contract. |
| `TOKEN_SYMBOL` | No | `TOKEN` | Used only in log output. |
| `POOL_ADDRESS` | **Yes** | — | The V3 pool address (USDC.e/your token). |
| `POOL_FEE` | **Yes** | `500` | V3 fee in 1/100 bps (100=0.01%, 500=0.05%, 3000=0.30%, 10000=1.00%). |
| `TOKEN_DECIMALS` | **Yes** | `6` | Token decimals. Most Doma tokens = 6, ETH-like = 18. |
| `USDCE_DECIMALS` | No | `6` | USDC.e is always 6. |
| `SWAP_SIZE_USD_MIN` | No | `5` | Lower bound of random swap size. |
| `SWAP_SIZE_USD_MAX` | No | `25` | Upper bound. |
| `SWAP_INTERVAL_SEC_MIN` | No | `60` | Lower bound of random sleep between swaps. |
| `SWAP_INTERVAL_SEC_MAX` | No | `300` | Upper bound. Don't go below 30. |
| `MAX_SLIPPAGE_PCT` | No | `0.005` (0.5%) | Abort swap if quoted output is worse than this. |
| `DAILY_LOSS_BUDGET_USD` | No | `5` | Halt for the day after this much cumulative cost. |
| `MIN_POOL_TVL_USD` | No | `5000` | Skip swap if pool TVL below this. |
| `MAX_SWAP_PCT_OF_TVL` | No | `0.005` (0.5%) | Skip swap if its size exceeds this fraction of TVL. |
| `MAX_SWAP_IMPACT_BPS` | No | `50` (0.5%) | Skip swap if estimated price impact exceeds this. |
| `DRY_RUN` | No | `true` | If true, no real transactions. Default-on for safety. |
| `LOG_LEVEL` | No | `INFO` | Standard Python log level. |

---

## Appendix E: How the bot picks direction and size (so the logs make sense)

Every cycle, the bot:

1. Reads the pool's current `slot0` (price, tick) and total liquidity.
2. Computes pool TVL by reading both token balances held by the pool contract.
3. Picks a random USD swap size in `[SWAP_SIZE_USD_MIN, SWAP_SIZE_USD_MAX]`.
4. Picks a random sleep duration in `[SWAP_INTERVAL_SEC_MIN, SWAP_INTERVAL_SEC_MAX]`.
5. Runs the safety checks (daily budget, pool TVL, max swap %).
6. Looks up the **last successful** swap's direction in the SQLite DB. If the last was `buy`, this one is `sell`. Otherwise `buy`. (First-ever swap defaults to `buy`.)
7. Computes the expected output using `slot0`'s price as a no-slippage baseline.
8. Sets `min_out = expected_out × (1 - MAX_SLIPPAGE_PCT)`.
9. Submits the swap through Permit2 + Universal Router with that `min_out`.
10. On success, parses the receipt's Transfer event to learn how much was actually received. Logs the cost (input USD - output USD).
11. Sleeps for the random interval.

Because direction strictly alternates based on the last successful swap, an extended run of failed swaps in one direction can cause the bot to repeatedly retry the same direction (it doesn't flip until at least one succeeds). If you see this, look at the recent log lines for what's failing — usually it's an `insufficient balance` warning meaning that side of the wallet has run out and you need to top it up.

---

## Appendix F: Rotating to a new wallet

You should rotate the bot's wallet periodically — every few months, or any time you have any reason to suspect the host might be compromised. Rotation is cheap; recovering from a compromise is not.

1. Generate a new wallet (Part 1 again).
2. Stop the bot:
   ```bash
   sudo supervisorctl stop volume_bot
   ```
3. Drain the old wallet by importing the old seed phrase into MetaMask, sending USDC.e + the token + ETH to the new wallet's address, and then removing the old wallet from MetaMask.
4. Edit `.env` and replace `MNEMONIC` with the new seed phrase.
5. Start the bot again:
   ```bash
   sudo supervisorctl start volume_bot
   ```
6. The bot will redo the one-time approvals against the new wallet (you'll see two extra transactions on the first cycle), then resume normal operation.

The SQLite DB is keyed by date, not wallet, so the daily totals will continue accumulating across the rotation seamlessly — the new wallet's swaps just get added to today's row.

---

## Appendix G: When *not* to run this bot

- **Your token is brand new and has no organic volume.** Volume that's 100% synthetic is more obvious than volume that's 95% synthetic. Wait until there's some real activity.
- **You're providing LP on the same pool.** You're paying yourself fees on every swap. Better to just LP and let real users generate volume.
- **You're trying to trigger a leaderboard or rank that explicitly excludes wash-traded volume.** Some leaderboards filter out single-wallet round-trips. Read the rules.
- **You don't have the daily budget you've configured.** If you set `DAILY_LOSS_BUDGET_USD=20` but only have $50 in the wallet, you'll burn through 40% of your inventory's value in a few days. Set the budget consistent with the funding you're willing to lose.
- **The pool fee is 1.00% or higher.** It's almost always better to wait for liquidity to migrate to a 0.05% pool than to pay 20× the cost on a 1% pool.

---

## Appendix H: A complete example of a healthy first hour

Below is what an actual first hour of bot operation should look like in the log. Use this as a reference for "healthy" output:

```
2026-05-13 12:00:01  INFO  ======================================================================
2026-05-13 12:00:01  INFO    Doma Volume Bot — MYDOM
2026-05-13 12:00:01  INFO  ======================================================================
2026-05-13 12:00:01  INFO    Pool:         0x...
2026-05-13 12:00:01  INFO    Fee tier:     0.050%
2026-05-13 12:00:01  INFO    Swap size:    $5.0-25.0
2026-05-13 12:00:01  INFO    Interval:     60-300s
2026-05-13 12:00:01  INFO    Daily budget: $5.0
2026-05-13 12:00:01  INFO    DRY RUN:      False
2026-05-13 12:00:02  INFO  Connected to RPC: chain_id=97477
2026-05-13 12:00:02  INFO    Wallet:       0xAbCd...1234
2026-05-13 12:00:03  INFO  [#1] direction=buy  size=$11.20  price=$0.001234  tvl=$15234  daily=$0.00vol/$0.0000cost
2026-05-13 12:00:04  INFO    Approving 0x31EEf89D → Permit2 (one-time)
2026-05-13 12:00:04  INFO    ERC20→Permit2 tx: 0x...
2026-05-13 12:00:08  INFO    ERC20→Permit2 ✓ block 12345
2026-05-13 12:00:08  INFO    Approving Permit2 0x31EEf89D → Router (one-time)
2026-05-13 12:00:09  INFO    Permit2→Router tx: 0x...
2026-05-13 12:00:13  INFO    Permit2→Router ✓ block 12346
2026-05-13 12:00:14  INFO    swap tx: 0x...
2026-05-13 12:00:18  INFO    swap ✓ block 12347
2026-05-13 12:00:18  INFO    swap ✓ received 9080000000 (raw)
2026-05-13 12:00:18  INFO    swap ✓ buy: in=$11.2000 out=$11.1944 cost=$0.0056
2026-05-13 12:00:18  INFO    sleeping 187s...
2026-05-13 12:03:25  INFO  [#2] direction=sell  size=$8.40  price=$0.001234  tvl=$15240  daily=$11.20vol/$0.0056cost
2026-05-13 12:03:26  INFO    Approving 0x... → Permit2 (one-time)
2026-05-13 12:03:26  INFO    ERC20→Permit2 tx: 0x...
2026-05-13 12:03:30  INFO    ERC20→Permit2 ✓ block 12350
2026-05-13 12:03:30  INFO    Approving Permit2 0x... → Router (one-time)
2026-05-13 12:03:31  INFO    Permit2→Router tx: 0x...
2026-05-13 12:03:35  INFO    Permit2→Router ✓ block 12351
2026-05-13 12:03:35  INFO    swap tx: 0x...
2026-05-13 12:03:39  INFO    swap ✓ block 12352
2026-05-13 12:03:39  INFO    swap ✓ received 8395000 (raw)
2026-05-13 12:03:39  INFO    swap ✓ sell: in=$8.4000 out=$8.3958 cost=$0.0042
2026-05-13 12:03:39  INFO    sleeping 142s...
2026-05-13 12:06:01  INFO  [#3] direction=buy  size=$17.30  price=$0.001234  tvl=$15238  daily=$19.60vol/$0.0098cost
2026-05-13 12:06:02  INFO    swap tx: 0x...
2026-05-13 12:06:06  INFO    swap ✓ block 12356
2026-05-13 12:06:06  INFO    swap ✓ received 14025000000 (raw)
2026-05-13 12:06:06  INFO    swap ✓ buy: in=$17.3000 out=$17.2913 cost=$0.0087
2026-05-13 12:06:06  INFO    sleeping 91s...
... (continues, no more approval lines because both tokens are now approved) ...
```

The key things to notice:

- Approvals only appear on the **first** swap of each token direction, then never again.
- After approvals, each swap is a single transaction.
- `daily=$X.XXvol/$Y.YYYYcost` ticks upward steadily.
- Direction strictly alternates `buy → sell → buy → sell ...`.
- `cost=$0.0XXX` is consistently ~0.05% of the input USD (matching the pool fee tier).

---

## Appendix I: One-page cheat sheet

Pin this to your wall.

```
INSTALL
  cd ~ && git clone <repo> && cd doma-volume-bot
  python3 -m venv .venv && source .venv/bin/activate
  pip install -r requirements.txt
  cp .env.example .env && nano .env && chmod 600 .env

DRY RUN
  source .venv/bin/activate
  python3 volume_bot.py --dry-run

LIVE (FOREGROUND)
  python3 volume_bot.py

LIVE (SUPERVISOR)
  sudo cp volume_bot.supervisor.conf.example /etc/supervisor/conf.d/volume_bot.conf
  sudo nano /etc/supervisor/conf.d/volume_bot.conf   # fix paths
  sudo supervisorctl reread && sudo supervisorctl update
  sudo supervisorctl start volume_bot

CONTROL
  sudo supervisorctl status volume_bot
  sudo supervisorctl restart volume_bot
  sudo supervisorctl stop volume_bot

LOGS
  sudo tail -f /var/log/supervisor/volume_bot.out.log

DAILY TOTALS
  sqlite3 ~/doma-volume-bot/volume_bot.db \
    "SELECT * FROM daily_totals ORDER BY date DESC LIMIT 7;"

WALLET BALANCES
  python3 -c "from web3 import Web3; from shared import connect, load_wallet, ERC20_ABI; \
    import config; w3=connect(); a=load_wallet()[0]; \
    u=w3.eth.contract(address=Web3.to_checksum_address(config.USDCE_ADDRESS),abi=ERC20_ABI); \
    t=w3.eth.contract(address=Web3.to_checksum_address(config.TOKEN_ADDRESS),abi=ERC20_ABI); \
    print(f'USDC.e {u.functions.balanceOf(a).call()/10**config.USDCE_DECIMALS:.4f}'); \
    print(f'TOK    {t.functions.balanceOf(a).call()/10**config.TOKEN_DECIMALS:.4f}'); \
    print(f'ETH    {w3.eth.get_balance(a)/10**18:.6f}')"

EMERGENCY STOP
  sudo supervisorctl stop volume_bot
  # Then drain wallet via MetaMask using seed from .env
```

---

## Appendix J: Frequently asked questions

### Will the bot work on testnet first?

The bot is hard-coded to Doma's chain ID via the `CHAIN_ID` env var (default `97477`, which is Doma mainnet). If a Doma testnet exists with its own chain ID, USDC.e contract, and Universal Router, you can in principle point the bot at testnet by changing `CHAIN_ID`, `RPC_URL`, `USDCE_ADDRESS`, and `UNIVERSAL_ROUTER` accordingly. In practice, dry-run mode against mainnet is a more reliable rehearsal because it uses the actual addresses and contracts you'll trade against — you just don't send transactions.

### How do I prove to my community that volume isn't all me?

You can't, fully — that's the honest answer. Anyone reading the chain can see that some volume is coming from a single wallet making symmetric round-trips. The mitigations are:

- Be transparent that you run a small volume bot if asked.
- Keep the bot's contribution small relative to organic volume — it should be a baseline, not the dominant source.
- Don't run the bot during major announcements or launches; you want organic volume to be unmistakably organic during those moments.

### Can I run multiple bots from one wallet?

Technically yes — the bot doesn't lock anything — but you'd be racing each other on nonces, hitting "nonce too low" errors constantly, and probably wasting gas. If you want to generate volume on multiple pools, run multiple bot instances each with **its own wallet**, each in its own directory with its own `.env`, each as a separate supervisor program.

### Can I run the bot against multiple pools from one process?

Not as written. The bot is single-pool by design (cleaner code, easier to reason about). For multi-pool operation, run multiple instances.

### What happens at midnight UTC?

The daily totals table is keyed by UTC date. At 00:00 UTC, the next swap creates a new row with fresh `cost_usd=0`, and the bot resumes trading even if it had been halted by yesterday's budget. This means your daily budget effectively resets at UTC midnight, not local midnight. If you want a local-time reset, you'd have to modify `state.py`.

### Why does the bot use Permit2 instead of just `approve(router, MAX)`?

Permit2 is the canonical Uniswap V3 approval pattern and is what the Universal Router expects. Direct ERC-20 approvals to the router would not work — the router itself is designed to call into Permit2 to pull tokens. The bot does the two-step approval (ERC20 → Permit2, Permit2 → Router) once per token, then never again until the year 2100.

### Why the +50% gas price multiplier?

The bot multiplies `eth.gas_price` by 1.5 to make sure transactions land quickly even during brief network congestion. Doma gas is sub-Gwei in normal conditions, so even a 50% premium is still a fraction of a cent per transaction. If you're operating at very high frequency and want to minimize gas spend, you could lower this in `volume_bot.py`, but for typical settings it's not worth optimizing.

### What if the RPC goes down for an extended period?

The bot's `connect()` function tries the primary RPC, falls back to the backup, and exits if neither works. If your RPC is down at startup, the bot exits and supervisor restarts it after `startsecs` (5 seconds) — and keeps restarting up to `startretries` (3 times). After 3 failures it goes `FATAL` and stays stopped. If you suspect RPC issues, check supervisor status and restart manually after the RPC recovers:

```bash
sudo supervisorctl restart volume_bot
```

Mid-loop RPC errors are caught by the `except Exception` in the main loop, logged, and the bot sleeps 30 seconds before retrying. You'd see these as `main loop exception:` lines in the log.

### What if Doma upgrades the Universal Router?

Eventually the Doma team may deploy a new Universal Router version. If they do, you'll need to update `UNIVERSAL_ROUTER` in your `.env`. The bot will fail to swap if pointed at an old/deprecated router; you'd see `swap failed (status=0)` repeatedly. Keep an eye on Doma's announcements channel for any router-address change announcements.

### Can I see all my historical swaps?

Yes — they're all in `volume_bot.db`:

```bash
sqlite3 ~/doma-volume-bot/volume_bot.db "SELECT id, executed_at, direction, amount_in_usd, amount_out_usd, cost_usd, status FROM swaps ORDER BY id DESC LIMIT 50;"
```

Or to export to CSV:

```bash
sqlite3 -header -csv ~/doma-volume-bot/volume_bot.db \
  "SELECT * FROM swaps;" > swap_history.csv
```

### Can I generate a daily report email?

Not built in. If you want one, you can write a small wrapper script that runs from cron, reads `daily_totals` from yesterday, and emails it to you. The bot's database is read-safe while the bot is running (SQLite WAL mode), so reading from it from a cron job is fine.

### What's the smallest safe daily volume target?

If your pool fee is 0.05%, the smallest meaningful daily volume target is around $500–$1,000/day at a cost of ~$0.50–$1.00. Below that, the per-swap minimums (gas, the bot's `100 raw units` floor) start mattering relative to swap size, and the volume looks small enough that it might not move any leaderboard or aggregator decision anyway.

### What's the largest practical daily volume target?

You'll hit a wall around 0.5% × pool TVL × cycles-per-day. For a $50k pool with `MAX_SWAP_PCT_OF_TVL=0.005` (0.5%), max swap is $250; with 60s minimum interval that's at most 1,440 swaps × $250 = ~$360k of one-way volume per day. Past that, you're either bumping into TVL limits or visibly dominating the pool and it stops looking organic. For really large daily targets, the right answer is to seed more LP first.

### Is there any way to use a hardware wallet?

Not as written. The bot signs transactions in-process with the private key derived from the seed in `.env`. Hardware wallets require user confirmation per transaction, which doesn't fit a 24/7 unattended bot. The mitigation is the dedicated-wallet pattern: keep the bot wallet small enough that a hot key is acceptable.

### What if I want to pause for an hour and resume?

Just stop and start:

```bash
sudo supervisorctl stop volume_bot
# wait an hour
sudo supervisorctl start volume_bot
```

The bot has no concept of a pause schedule. If you want to pause it on a recurring schedule (e.g., quiet hours), you'd write cron jobs that issue start/stop via supervisorctl.

### Why does the first swap take so much longer than subsequent ones?

The first swap of a token requires two approval transactions before the actual swap, so you're seeing 3 transactions back-to-back instead of 1. Each one waits for confirmation. After both approvals are confirmed, all future swaps of that token are a single transaction. After the bot has done at least one buy and one sell, no more approvals are ever needed (assuming the canonical Permit2 expiration in 2100 doesn't lapse).

### Can two different tokens share approvals?

No — Permit2 approvals are per-token. The bot will do the two-step approval once for USDC.e (during the first buy) and once for your domain token (during the first sell). After that, both directions are single-transaction swaps.

### What's the relationship between `MAX_SWAP_PCT_OF_TVL` and `MAX_SWAP_IMPACT_BPS`?

They're two angles on the same concern: don't move the pool price too much per swap. `MAX_SWAP_PCT_OF_TVL` is a coarse pre-check on swap size relative to total liquidity. `MAX_SWAP_IMPACT_BPS` (currently a soft check that's mostly informational in this version of the bot) is a finer-grained estimate of actual price impact. In practice, the `MAX_SWAP_PCT_OF_TVL` check fires first and reliably, so you'll rarely see the impact check kick in.

### What format should `MNEMONIC` be in?

Plain text, all words separated by single spaces, no leading/trailing whitespace, no quotes:

```
MNEMONIC=word1 word2 word3 word4 word5 word6 word7 word8 word9 word10 word11 word12
```

Both 12-word and 24-word mnemonics work. The derivation path is the standard Ethereum BIP-44 path `m/44'/60'/0'/0/{MNEMONIC_ACCOUNT_INDEX}`, which matches what MetaMask and most other wallets use by default.

### Can I read swap data from the SQLite DB while the bot is running?

Yes. The bot uses SQLite's WAL (Write-Ahead Logging) mode, which allows concurrent readers and a single writer without blocking. Run `sqlite3 ~/doma-volume-bot/volume_bot.db "SELECT ..."` any time, even mid-swap.

### What if I lose my .env?

If your `.env` file is destroyed (disk failure, accidental `rm`) but you still have your seed phrase written down on paper:

1. Re-create `.env` from `.env.example`.
2. Paste your mnemonic back into the `MNEMONIC=` line.
3. Re-fill the `TOKEN_ADDRESS`, `POOL_ADDRESS`, `POOL_FEE`, `TOKEN_DECIMALS` from doma.xyz.
4. Restart the bot.

The wallet is recoverable from the seed phrase. The SQLite history is just historical totals — if it's also lost, the bot starts over with `daily_totals` empty (which simply means today's budget tracker resets to 0). No funds are lost.

### What if I lose my seed phrase?

If you lose both your seed phrase and your `.env` file, the funds in the wallet are gone — there is no recovery mechanism. **Write the seed on paper. Keep it somewhere safe. Test that you can read your handwriting.**

---

## Final word

Volume bots are tools. Used responsibly — small budget, dedicated wallet, transparent intent — they fill a real gap for small projects on emerging chains. Used irresponsibly — main wallet's seed in `.env`, no daily budget, dishonest claims to your community — they will eventually cost you a wallet, a community, or both.

Start with `DRY_RUN=true`. Start with $50 in each side. Start with the default $5/day budget. Watch the logs for a week. Then tune.

If you've followed this guide end-to-end and something still doesn't work, the answer is almost always either (a) a wrong value in `.env`, (b) the bot wallet is missing inventory or gas, or (c) the pool address points at the wrong pool. Re-check those three things before assuming the bot itself is broken.

Good luck, and trade responsibly.
