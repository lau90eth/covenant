# Covenant — Milestone-Gated Grants

A grant releases funds when a milestone is independently verified against real-world evidence — not on a calendar, and not on a trustee's say-so. GenLayer's leader and validator each check that evidence on their own and must agree before any GEN moves.

## Smart Contract

**Deployed:** `0x3E5e258FA394fC9f51f5593728F8B06705AdC197` · GenLayer Bradbury Testnet

Source: [`covenant.py`](./covenant.py)

### Deploy

```bash
genlayer deploy --contract covenant.py
```

### Interact

`add_tranche` is payable — it escrows the GEN for that milestone. The `genlayer write` CLI currently hardcodes transaction value to `0`, so funding a tranche isn't possible through it — use `genlayer-js` directly:

```js
import { createClient } from 'genlayer-js';
import { testnetBradbury } from 'genlayer-js/chains';

const client = createClient({ chain: testnetBradbury });
await client.writeContract({
  account: { address: '0xYourAddress', type: 'json-rpc' },
  address: '0x3E5e258FA394fC9f51f5593728F8B06705AdC197',
  functionName: 'add_tranche',
  args: ['0', 'Milestone description', 'https://evidence.url'],
  value: 1000000000000000000n, // 1 GEN, in wei
});
```

Everything else is non-payable and works through the CLI:

```bash
# Register a grantor -> recipient relationship (no funds move yet)
genlayer write <CONTRACT_ADDRESS> create_grant --args 0xRecipientAddress

# Recipient claims a tranche — triggers leader + validator to independently judge it
genlayer write <CONTRACT_ADDRESS> claim_tranche --args 0 0

# Grantor reclaims an unclaimed tranche
genlayer write <CONTRACT_ADDRESS> cancel_tranche --args 0 0

# Read
genlayer call <CONTRACT_ADDRESS> get_grant --args 0
genlayer call <CONTRACT_ADDRESS> get_tranche --args 0 0
genlayer call <CONTRACT_ADDRESS> get_grant_count
```

## How it works

1. **Create a grant** — the grantor registers a recipient. No funds move yet.
2. **Add a tranche** — the grantor escrows GEN for one specific milestone, described in plain language, with a link to how it will be verified. A grant can have any number of tranches, added over time.
3. **Claim** — the recipient triggers a claim once the milestone is met. The leader fetches the evidence URL and judges; the validator independently fetches the same URL and judges again. The tranche only releases if both agree the milestone is satisfied — not if the leader's judgment merely looks reasonable.
4. **Retry or cancel** — if the evidence doesn't support the claim yet, the tranche stays open and the recipient can claim again later. If the grantor wants out before that happens, `cancel_tranche` refunds the escrow — but only while the tranche is still open; once released, it's final.

## Contract Methods

| Method | Type | Description |
|--------|------|-------------|
| `create_grant(recipient)` | write | Register a grantor → recipient relationship |
| `add_tranche(grant_id, description, evidence_url)` | write, payable | Escrow GEN for one milestone on an existing grant |
| `claim_tranche(grant_id, tranche_id)` | write | Recipient only. Leader and validator independently judge whether the milestone is met; pays out on agreement |
| `cancel_tranche(grant_id, tranche_id)` | write | Grantor only, while still open. Refunds the escrow |
| `get_grant(grant_id)` | view | Grantor, recipient, and tranche count |
| `get_tranche(grant_id, tranche_id)` | view | Description, evidence URL, status, and amount |
| `get_grant_count()` | view | Total number of grants created |

## Why milestones, not a calendar

Time-based vesting doesn't need an Intelligent Contract — a deterministic contract already handles "unlock at block N" on every chain, no judgment required. What a normal contract *can't* do is check whether a team actually shipped a release, whether a metric on a public dashboard crossed a threshold, or whether a deliverable matches what was promised — those need reading and reasoning about something on the internet, not just watching the clock. Covenant is built around evidence, not timestamps, on purpose: it only does the part a deterministic contract genuinely can't.

## Tech Stack

- GenLayer Intelligent Contract (Python), flat `TreeMap[str, str]` storage for grants and tranches
- LLM consensus via `gl.nondet.exec_prompt`; evidence fetched independently by leader and validator via `gl.nondet.web.get`
- Payouts and refunds via the EVM transfer interface (`gl.evm.contract_interface` / `EthAccount.emit_transfer`)

## Network

GenLayer Bradbury Testnet (Chain ID: 4221)
- RPC: `https://rpc-bradbury.genlayer.com`
- Explorer: `https://explorer-bradbury.genlayer.com`

## Testing

All three outcomes were verified on Bradbury with two genuinely distinct wallets (grantor and recipient), checked against wallet balance deltas and on-chain state — not the write-transaction's own status fields:

- **Approved claim:** a tranche's evidence supported its milestone. The recipient's balance rose by the tranche amount (net of gas), the contract's balance returned to exactly zero, and `get_tranche` showed `Status: released`.
- **Rejected claim:** a tranche's evidence did *not* support its milestone. No GEN moved, the tranche's escrow stayed in the contract, and `get_tranche` showed `Status: open` — available to claim again.
- **Cancellation:** the grantor reclaimed a still-open tranche. The escrow returned to the grantor (net of gas) and `get_tranche` showed `Status: cancelled`.
