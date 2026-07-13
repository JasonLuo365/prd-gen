"""Acceptance-contract phase for PRD generation.

This phase captures business oracles. It deliberately does not generate Gherkin;
the downstream test-generation skill owns TC and Gherkin rendering.
"""
from typing import Any

from prd_flow.phases.base import Phase
from prd_flow.quality.oracle import check_oracle_coverage, validate_acceptance_contract


class AcceptancePhase(Phase):
    @property
    def phase_id(self) -> str:
        return "P4"

    @property
    def phase_name(self) -> str:
        return "Acceptance Contracts"

    def run(self) -> dict[str, Any]:
        """Collect explicit contract fields without synthesizing missing answers."""
        print("\n[Acceptance Contracts] 输入 done 结束。\n")
        contracts: list[dict] = []
        while True:
            req_id = input("关联需求 ID：").strip()
            if req_id.lower() == "done":
                break
            contract_type = input("类型（functional/nfr）：").strip().lower() or "functional"
            contract_id = input("契约 ID：").strip() or f"AC-{len(contracts) + 1:03d}"
            evidence_refs = [x.strip() for x in input("证据引用（逗号分隔）：").split(",") if x.strip()]
            if contract_type == "nfr":
                contract = {
                    "id": contract_id,
                    "type": "nfr",
                    "verifies": [req_id],
                    "release_scope": "current",
                    "population": input("测量总体/样本：").strip(),
                    "measurement_start": input("测量起点：").strip(),
                    "measurement_end": input("测量终点：").strip(),
                    "unit": input("单位：").strip(),
                    "threshold": input("阈值：").strip(),
                    "exclusions": [x.strip() for x in input("排除项（逗号分隔）：").split(",") if x.strip()],
                    "pass_rule": input("通过规则：").strip(),
                    "evidence_refs": evidence_refs,
                }
            else:
                contract = {
                    "id": contract_id,
                    "type": "functional",
                    "verifies": [req_id],
                    "release_scope": "current",
                    "actor": input("参与者：").strip(),
                    "preconditions": [x.strip() for x in input("前置条件（逗号分隔）：").split(",") if x.strip()],
                    "trigger": input("触发动作：").strip(),
                    "response": [x.strip() for x in input("系统响应（逗号分隔）：").split(",") if x.strip()],
                    "observable_oracles": [x.strip() for x in input("可观察判定（逗号分隔）：").split(",") if x.strip()],
                    "boundaries": [x.strip() for x in input("边界及对应响应（逗号分隔）：").split(",") if x.strip()],
                    "exceptions": [x.strip() for x in input("异常及对应响应（逗号分隔）：").split(",") if x.strip()],
                    "evidence_refs": evidence_refs,
                }
            issues = validate_acceptance_contract(contract)
            if issues:
                print("契约不完整，未保存：" + "; ".join(issues))
                continue
            contracts.append(contract)
        return self.collect(contracts=contracts)

    def collect(self, contracts: list[dict]) -> dict:
        data = {"contracts": contracts}
        self.update_state(data)
        return data

    def check_minimum_standard(self, data: dict[str, Any]) -> tuple[bool, str]:
        requirements = self.state.draft_content.get("P3", {})
        contracts = data.get("contracts", [])
        invalid = {
            contract.get("id", "UNKNOWN"): validate_acceptance_contract(contract)
            for contract in contracts
            if validate_acceptance_contract(contract)
        }
        if invalid:
            details = "; ".join(f"{key}: {', '.join(value)}" for key, value in invalid.items())
            return False, f"Acceptance Contract 字段不完整：{details}"
        gaps = check_oracle_coverage(requirements, contracts)
        if gaps:
            details = "; ".join(f"{gap['id']}: {gap['reason']}" for gap in gaps)
            return False, f"当前版本需求缺少完整判定依据：{details}"
        return True, "所有当前版本功能与 NFR 均有完整 Acceptance Contract"
