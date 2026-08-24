# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
from genlayer import *

@gl.evm.contract_interface
class EthAccount:
    class View:
        pass
    class Write:
        pass

class Covenant(gl.Contract):
    grant_count: u256

    # "{grant_id}:field" -> value. Fields: grantor, recipient, tranche_count
    grants: TreeMap[str, str]
    # "{grant_id}:{tranche_id}:field" -> value. Fields: description, evidence_url, status, amount
    tranches: TreeMap[str, str]

    def __init__(self):
        self.grant_count = u256(0)
        self.grants = TreeMap()
        self.tranches = TreeMap()

    @gl.public.write
    def create_grant(self, recipient: str) -> None:
        """Registers a grantor -> recipient relationship. No funds move here —
        fund individual milestones afterward via add_tranche."""
        gid = str(self.grant_count)
        self.grants[f"{gid}:grantor"] = str(gl.message.sender_address)
        self.grants[f"{gid}:recipient"] = str(recipient)
        self.grants[f"{gid}:tranche_count"] = "0"
        self.grant_count = self.grant_count + u256(1)

    @gl.public.write.payable
    def add_tranche(self, grant_id: str, description: str, evidence_url: str) -> None:
        """Only the grantor. Escrows gl.message.value as this tranche's payout,
        released only when the recipient produces evidence the milestone is met."""
        gid = str(grant_id)
        grantor = self.grants.get(f"{gid}:grantor", "")
        if grantor == "":
            raise Exception("Grant not found")
        if str(gl.message.sender_address) != grantor:
            raise Exception("Only the grantor can add a tranche")
        amount = gl.message.value
        if amount == u256(0):
            raise Exception("Must escrow a nonzero amount")

        tid = self.grants.get(f"{gid}:tranche_count", "0")
        self.tranches[f"{gid}:{tid}:description"] = str(description)[:300]
        self.tranches[f"{gid}:{tid}:evidence_url"] = str(evidence_url)[:300]
        self.tranches[f"{gid}:{tid}:status"] = "open"
        self.tranches[f"{gid}:{tid}:amount"] = str(amount)
        self.grants[f"{gid}:tranche_count"] = str(int(tid) + 1)

    @gl.public.write
    def claim_tranche(self, grant_id: str, tranche_id: str) -> None:
        """Only the recipient. Leader and validator each independently fetch
        evidence_url and judge whether the milestone description is satisfied."""
        gid = str(grant_id)
        tid = str(tranche_id)
        recipient = self.grants.get(f"{gid}:recipient", "")
        if recipient == "":
            raise Exception("Grant not found")
        if str(gl.message.sender_address) != recipient:
            raise Exception("Only the grant's recipient can claim")
        status = self.tranches.get(f"{gid}:{tid}:status", "")
        if status != "open":
            raise Exception("Tranche is not open")

        description = self.tranches.get(f"{gid}:{tid}:description", "")
        evidence_url = self.tranches.get(f"{gid}:{tid}:evidence_url", "")
        ask = (f"Milestone: {description}\n"
               f"Based only on the evidence above, has this milestone been achieved? "
               f"Answer only TRUE or FALSE.")

        def _norm(s: str) -> str:
            return ''.join(c for c in s.upper() if c.isalpha())

        def leader_fn() -> str:
            page = gl.nondet.web.get(evidence_url).body.decode('utf-8', errors='replace')[:3000]
            prompt = f"Evidence:\n\n{page}\n\n{ask}"
            raw = gl.nondet.exec_prompt(prompt)
            normalized = _norm(raw.replace('\x00', '').strip())
            if "TRUE" in normalized:
                return "TRUE"
            return "FALSE"

        def validator_fn(leaders_res) -> bool:
            if not isinstance(leaders_res, gl.vm.Return):
                return False
            leader_answer = leaders_res.calldata
            if not isinstance(leader_answer, str):
                return False
            page = gl.nondet.web.get(evidence_url).body.decode('utf-8', errors='replace')[:3000]
            prompt = f"Evidence:\n\n{page}\n\n{ask}"
            raw = gl.nondet.exec_prompt(prompt)
            normalized = _norm(raw.replace('\x00', '').strip())
            validator_answer = "TRUE" if "TRUE" in normalized else "FALSE"
            return validator_answer == leader_answer.strip().upper()

        result = gl.vm.run_nondet_unsafe(leader_fn, validator_fn)
        verdict = result.replace('\x00', '').strip()

        if verdict == "TRUE":
            self.tranches[f"{gid}:{tid}:status"] = "released"
            amount = u256(int(self.tranches.get(f"{gid}:{tid}:amount", "0")))
            if amount > u256(0):
                EthAccount(gl.Address(recipient)).emit_transfer(value=amount)
        # FALSE: status stays "open" — recipient can retry later with better evidence

    @gl.public.write
    def cancel_tranche(self, grant_id: str, tranche_id: str) -> None:
        """Only the grantor, only while the tranche is still open (unclaimed).
        Refunds the escrowed amount back to the grantor."""
        gid = str(grant_id)
        tid = str(tranche_id)
        grantor = self.grants.get(f"{gid}:grantor", "")
        if grantor == "":
            raise Exception("Grant not found")
        if str(gl.message.sender_address) != grantor:
            raise Exception("Only the grantor can cancel")
        status = self.tranches.get(f"{gid}:{tid}:status", "")
        if status != "open":
            raise Exception("Only an open tranche can be cancelled")
        self.tranches[f"{gid}:{tid}:status"] = "cancelled"
        amount = u256(int(self.tranches.get(f"{gid}:{tid}:amount", "0")))
        if amount > u256(0):
            EthAccount(gl.Address(grantor)).emit_transfer(value=amount)

    @gl.public.view
    def get_grant(self, grant_id: str) -> str:
        gid = str(grant_id)
        grantor = self.grants.get(f"{gid}:grantor", "")
        if grantor == "":
            return "not found"
        recipient = self.grants.get(f"{gid}:recipient", "")
        tranche_count = self.grants.get(f"{gid}:tranche_count", "0")
        return f"Grantor: {grantor} | Recipient: {recipient} | Tranches: {tranche_count}"

    @gl.public.view
    def get_tranche(self, grant_id: str, tranche_id: str) -> str:
        gid = str(grant_id)
        tid = str(tranche_id)
        description = self.tranches.get(f"{gid}:{tid}:description", "")
        if description == "":
            return "not found"
        evidence_url = self.tranches.get(f"{gid}:{tid}:evidence_url", "")
        status = self.tranches.get(f"{gid}:{tid}:status", "")
        amount = self.tranches.get(f"{gid}:{tid}:amount", "0")
        return f"Description: {description} | Evidence: {evidence_url} | Status: {status} | Amount: {amount}"

    @gl.public.view
    def get_grant_count(self) -> str:
        return str(self.grant_count)
