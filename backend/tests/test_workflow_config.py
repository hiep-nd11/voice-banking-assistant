import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml
from langchain_core.prompts import PromptTemplate

from app.agent import workflows
from app.agent.memory import Session
from app.agent.prompts import PROMPT_PATH, build_system_prompt, load_system_prompt
from app.agent.workflow_config import CONFIG_PATH, WorkflowConfig, load_workflow_config


class WorkflowConfigTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

    def test_rules_are_editable_without_changing_intent_code(self):
        self.data["rules"].insert(
            0, {"intent": "balance", "when": {"pattern": "custom balance phrase"}}
        )
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "workflows.json"
            path.write_text(json.dumps(self.data), encoding="utf-8")
            loaded = load_workflow_config(path)
        with patch.object(workflows, "CONFIG", loaded):
            self.assertEqual(workflows.intent_for("custom balance phrase"), "balance")
            self.assertIsNone(workflows.intent_for("cach chuyen tien"))

    def test_invalid_references_and_templates_fail_at_load(self):
        mutations = [
            lambda data: data["rules"][0].update(intent="missing"),
            lambda data: data["scenarios"]["balance"].update(screen="unknown"),
            lambda data: data["scenarios"]["balance"].update(lookup="execute_transfer"),
            lambda data: data["messages"].update(recipient_not_found="Wrong {recipient}"),
            lambda data: data["messages"].pop("ask_amount"),
            lambda data: data["scenarios"]["open_savings"]["requirements"][0].update(
                message="missing"
            ),
        ]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                data = copy.deepcopy(self.data)
                mutate(data)
                with self.assertRaises(ValueError):
                    WorkflowConfig.model_validate(data)

    def test_prompt_is_loaded_from_external_text(self):
        definition = yaml.safe_load(PROMPT_PATH.read_text(encoding="utf-8"))
        prompt = load_system_prompt()
        self.assertIsInstance(prompt, PromptTemplate)
        self.assertEqual(prompt.metadata["prompt_version"], definition["version"])
        self.assertEqual(build_system_prompt(3), definition["template"].replace("{max_steps}", "3"))

    def test_prompt_rejects_undeclared_variables_and_wrong_template_format(self):
        original = yaml.safe_load(PROMPT_PATH.read_text(encoding="utf-8"))
        for update in (
            {"template": "Unknown {customer}"},
            {"template": "Missing input"},
            {"template_format": "jinja2"},
        ):
            with self.subTest(update=update), tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / "prompt.yaml"
                path.write_text(yaml.safe_dump({**original, **update}), encoding="utf-8")
                with self.assertRaises(ValueError):
                    load_system_prompt(path)


class ConfiguredStepTests(unittest.IsolatedAsyncioTestCase):
    async def test_config_controls_required_step_message_and_navigation(self):
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        data["messages"]["ask_amount"] = "Custom amount prompt"
        data["scenarios"]["transfer_account"]["step_screens"]["awaiting_amount"] = "workflow"
        config = WorkflowConfig.model_validate(data)
        session = Session(session_id="config-test", customer_id=2)
        session.workflow = {
            "id": "flow",
            "intent": "transfer_account",
            "step": "starting",
            "version": 0,
            "slots": {"destination": {"account": "123456789", "bank": "Vietcombank"}},
        }
        with (
            patch.object(workflows, "CONFIG", config),
            patch.object(
                workflows,
                "workflow_message",
                lambda key, **values: config.messages[key].format(**values),
            ),
        ):
            events = await workflows.advance(session)
        self.assertEqual(session.workflow["step"], "awaiting_amount")
        self.assertTrue(any(row.get("content") == "Custom amount prompt" for row in events))
        self.assertTrue(any(row.get("screen") == "workflow" for row in events))
