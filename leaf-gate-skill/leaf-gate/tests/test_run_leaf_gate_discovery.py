import tempfile
import unittest
from pathlib import Path

from scripts import run_leaf_gate


class ArchitectureDiscoveryTests(unittest.TestCase):
    def test_root_output_directory_is_architecture_package(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            node_dir = Path(tmp)
            (node_dir / "prd.md").write_text(
                "# Requirements\n\n- [REQ-001] System uploads a file.\n",
                encoding="utf-8",
            )
            (node_dir / "custom-name.feature").write_text(
                "Feature: upload\n\n"
                "  @REQ-001\n"
                "  Scenario: upload file\n"
                "    Given a file\n"
                "    When the user uploads it\n"
                "    Then the system accepts the file\n",
                encoding="utf-8",
            )
            output_dir = node_dir / "output"
            output_dir.mkdir()
            contract = output_dir / "06-interface-contracts.md"
            contract.write_text(
                "# Interface Contracts\n\n"
                "- inputs: file\n"
                "- outputs: uploadId\n"
                "- errors: invalid file\n"
                "- states: uploaded\n"
                "- side_effects: stores metadata\n"
                "- dependencies: object storage\n",
                encoding="utf-8",
            )

            artifacts = run_leaf_gate.find_artifacts(node_dir)
            report = run_leaf_gate.build_report(node_dir, None)

            self.assertEqual(artifacts.feature, node_dir / "custom-name.feature")
            self.assertEqual(artifacts.architecture, output_dir)
            self.assertIn(contract, artifacts.architecture_files)
            self.assertNotIn("architecture", report["static_checks"]["artifacts"]["missing"])

    def test_explicit_artifact_paths_override_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            node_dir = Path(tmp)
            prd = node_dir / "product-requirements.md"
            feature = node_dir / "acceptance.feature"
            arch = node_dir / "archdocs"
            prd.write_text("REQ-001: System supports upload.\n", encoding="utf-8")
            feature.write_text(
                "Feature: upload\n\n"
                "  @REQ-001\n"
                "  Scenario: upload file\n"
                "    Given a file\n"
                "    When the user uploads it\n"
                "    Then the system returns uploadId\n",
                encoding="utf-8",
            )
            arch.mkdir()
            (arch / "contracts.md").write_text(
                "- inputs: file\n"
                "- outputs: uploadId\n"
                "- errors: invalid file\n"
                "- states: uploaded\n"
                "- side_effects: stores metadata\n"
                "- dependencies: object storage\n",
                encoding="utf-8",
            )

            report = run_leaf_gate.build_report(
                node_dir,
                None,
                prd_path=Path("product-requirements.md"),
                feature_path=Path("acceptance.feature"),
                architecture_path=Path("archdocs"),
            )

            artifacts = report["static_checks"]["artifacts"]
            self.assertEqual(artifacts["prd"], str(prd))
            self.assertEqual(artifacts["feature"], str(feature))
            self.assertEqual(artifacts["architecture"], str(arch))
            self.assertNotIn("prd", artifacts["missing"])
            self.assertNotIn("feature", artifacts["missing"])
            self.assertNotIn("architecture", artifacts["missing"])

    def test_generic_requirement_formats_and_could_have_are_parsed(self) -> None:
        requirements = run_leaf_gate.extract_requirements(
            "# Requirements\n\n"
            "## Must Have\n"
            "REQ-001: Colon format requirement.\n\n"
            "### REQ-002 - Heading format requirement\n\n"
            "| ID | Requirement |\n"
            "| --- | --- |\n"
            "| NFR-001 | Table format requirement |\n\n"
            "## Could Have\n"
            "- [REQ-003] Deferred analytics requirement.\n"
        )

        by_id = {item["id"]: item for item in requirements}
        self.assertEqual(sorted(by_id), ["NFR-001", "REQ-001", "REQ-002", "REQ-003"])
        self.assertEqual(by_id["REQ-003"]["status"], "deferred")

    def test_canonical_models_are_exposed_by_parsers(self) -> None:
        requirements = run_leaf_gate.parse_requirements("REQ-001: Upload a file.\n", "prd.md")
        scenarios, parser_name = run_leaf_gate.parse_scenarios(
            "Feature: upload\n\n"
            "  @REQ-001\n"
            "  Scenario: upload file\n"
            "    Given a file\n"
            "    When the user uploads it\n"
            "    Then response contains uploadId\n",
            "testcase.feature",
        )

        self.assertIsInstance(requirements[0], run_leaf_gate.Requirement)
        self.assertIsInstance(scenarios[0], run_leaf_gate.Scenario)
        self.assertIn(parser_name, {"fallback", "gherkin-official"})
        self.assertEqual(scenarios[0].requirement_ids, ["REQ-001"])
        self.assertEqual(scenarios[0].source.artifact, "testcase.feature")

    def test_fallback_gherkin_parser_handles_outline_examples_and_adjacent_tags(self) -> None:
        report = run_leaf_gate.parse_feature(
            "Feature: checkout\n\n"
            "  @REQ-001 @MET-001\n"
            "  Scenario Outline: priced checkout\n"
            "    Given a cart with <count> items\n"
            "    When checkout starts\n"
            "    Then response contains orderId\n"
            "    Examples:\n"
            "      | count |\n"
            "      | 1     |\n"
            "  @REQ-002\n"
            "  Scenario: reject empty cart\n"
            "    Given an empty cart\n"
            "    When checkout starts\n"
            "    Then error code EMPTY_CART is returned\n"
        )

        self.assertEqual(report["scenario_count"], 2)
        self.assertEqual(report["scenario_outline_count"], 1)
        self.assertEqual(report["expanded_case_count"], 2)
        self.assertEqual(report["scenarios"][0]["req_tags"], ["REQ-001"])
        self.assertEqual(report["scenarios"][1]["req_tags"], ["REQ-002"])

    def test_profile_config_supplies_project_trace_terms(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            node_dir = Path(tmp)
            (node_dir / "prd.md").write_text(
                "REQ-001: Customer completes frobnicate receipt flow.\n",
                encoding="utf-8",
            )
            (node_dir / "testcase.feature").write_text(
                "Feature: frobnicate\n\n"
                "  @REQ-001\n"
                "  Scenario: complete flow\n"
                "    Given a ready request\n"
                "    When the customer confirms it\n"
                "    Then response contains receiptId\n",
                encoding="utf-8",
            )
            output_dir = node_dir / "output"
            output_dir.mkdir()
            (output_dir / "contracts.md").write_text(
                "- inputs: request\n"
                "- outputs: receiptId\n"
                "- errors: invalid request\n"
                "- states: completed\n"
                "- side_effects: writes audit record\n"
                "- dependencies: bar-service\n",
                encoding="utf-8",
            )
            (node_dir / "leaf-gate.config.json").write_text(
                '{"profile_path": "leaf-gate.profile.json"}',
                encoding="utf-8",
            )
            (node_dir / "leaf-gate.profile.json").write_text(
                '{'
                '"trace_terms": ["frobnicate", "receipt"],'
                '"trace_synonyms": {"frobnicate": ["bar-service"], "receipt": ["receiptId"]},'
                '"architecture_markers": ["bar-service"]'
                '}',
                encoding="utf-8",
            )

            report = run_leaf_gate.build_report(node_dir, None)

            c4 = report["static_checks"]["C4_verifiability"]["evidence"]
            self.assertEqual(c4["architecture_evidence_gaps"], [])
            self.assertEqual(report["config"]["profile_path"], str(node_dir / "leaf-gate.profile.json"))
            self.assertIn("frobnicate", report["config"]["profile"]["trace_terms"])

    def test_scenario_points_drive_decomposition(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            node_dir = Path(tmp)
            (node_dir / "prd.md").write_text(
                "\n".join(f"- [REQ-{index:03d}] Requirement {index}." for index in range(1, 7)),
                encoding="utf-8",
            )
            (node_dir / "testcase.feature").write_text(
                "Feature: broad\n\n"
                "  @COMP-001 @REQ-001 @REQ-002 @REQ-003 @REQ-004\n"
                "  Scenario: composite workflow\n"
                "    Given state one\n"
                "    When action one\n"
                "    Then result one\n\n"
                "  @REQ-005\n"
                "  Scenario: second workflow\n"
                "    Given state two\n"
                "    When action two\n"
                "    Then result two\n\n"
                "  @REQ-006\n"
                "  Scenario: third workflow\n"
                "    Given state three\n"
                "    When action three\n"
                "    Then result three\n",
                encoding="utf-8",
            )
            output_dir = node_dir / "output"
            output_dir.mkdir()
            (output_dir / "06-interface-contracts.md").write_text(
                "REQ-001 REQ-002 REQ-003 REQ-004 REQ-005 REQ-006\n"
                "- inputs: request\n"
                "- outputs: response\n"
                "- errors: error\n"
                "- states: active\n"
                "- side_effects: writes record\n"
                "- dependencies: database\n",
                encoding="utf-8",
            )
            (node_dir / "leaf-gate.config.json").write_text(
                '{"thresholds": {"max_scenario_points": 2}}',
                encoding="utf-8",
            )

            report = run_leaf_gate.build_report(node_dir, None)

            self.assertEqual(report["decision"], "CONTINUE_LAYERING")
            self.assertIn("split-composite-cross-requirement-scenarios", report["next_action"]["children"])
            self.assertGreater(report["static_checks"]["C1_behavior_complexity"]["evidence"]["scenario_points"], 2)

    def test_decomposition_markdown_is_written_for_decomposition(self) -> None:
        report = {
            "node_id": "node",
            "decision": "CONTINUE_LAYERING",
            "summary": "too broad",
            "static_checks": {
                "C1_behavior_complexity": {
                    "reason": "scenario points exceed threshold",
                    "evidence": {
                        "scenario_count": 3,
                        "scenario_points": 9,
                        "composite_scenario_count": 1,
                        "metric_only_scenario_count": 0,
                    },
                },
                "C3_ai_context_control": {
                    "reason": "implementation pack context exceeds threshold",
                    "evidence": {"implementation_pack_tokens": 20000, "full_artifact_tokens": 50000},
                },
                "C5_risk_decomposition": {
                    "reason": "Static risk thresholds passed.",
                    "evidence": {"high_risk_classes": ["security_auth"]},
                },
            },
            "next_action": {
                "type": "decompose",
                "children": ["split-by-behavior-family"],
                "notes": [],
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            run_leaf_gate.write_decision_markdown_files(report, out)
            text = (out / "leaf-gate.decomposition.md").read_text(encoding="utf-8")

        self.assertIn("Leaf Gate Decomposition Suggestions", text)
        self.assertIn("split-by-behavior-family", text)


if __name__ == "__main__":
    unittest.main()
