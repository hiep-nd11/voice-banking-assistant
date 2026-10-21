"""Validated, declarative workflow configuration. Loaded once at startup."""

import json
import re
from pathlib import Path
from string import Formatter
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "workflows.json"
SCREENS = {
    "home",
    "assets",
    "savings",
    "loans",
    "history",
    "finance",
    "analytics",
    "recipients",
    "qr",
    "transfer",
    "workflow",
}
LOOKUPS = {"get_account_balances", "get_recent_transactions", "get_month_overview"}


class Requirement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    slot: Literal["qr", "destination.account", "destination.bank", "amount", "term_months"]
    step: Literal[
        "awaiting_qr", "awaiting_account", "awaiting_bank", "awaiting_amount", "awaiting_term"
    ]
    message: str
    screen: Literal["qr", "transfer", "workflow"] = "workflow"


class Scenario(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["flow", "navigation"]
    screen: str | None = None
    feature: Literal["budget"] | None = None
    lookup: str | None = None
    clear_pending: bool = False
    minimum: int = Field(default=1000, ge=1000)
    terms: list[int] = Field(default_factory=list)
    max_term: int = Field(default=300, ge=1, le=300)
    requirements: list[Requirement] = Field(default_factory=list)
    step_screens: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_targets(self):
        if self.screen is not None and self.screen not in SCREENS:
            raise ValueError(f"Unknown screen: {self.screen}")
        if any(screen not in SCREENS for screen in self.step_screens.values()):
            raise ValueError("Unknown step screen")
        if self.kind == "navigation" and not self.screen:
            raise ValueError("Navigation requires a screen")
        if self.lookup is not None and self.lookup not in LOOKUPS:
            raise ValueError(f"Unknown lookup: {self.lookup}")
        if any(type(term) is not int or not 1 <= term <= 300 for term in self.terms):
            raise ValueError("Invalid term")
        return self


class Condition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pattern: str | None = None
    predicate: Literal["has_destination", "has_recipient"] | None = None
    all: list["Condition"] | None = None
    any: list["Condition"] | None = None

    @model_validator(mode="after")
    def validate_condition(self):
        if (
            sum(value is not None for value in (self.pattern, self.predicate, self.all, self.any))
            != 1
        ):
            raise ValueError("Condition must have exactly one operation")
        if self.pattern is not None:
            re.compile(self.pattern)
        if self.all == [] or self.any == []:
            raise ValueError("Empty condition group")
        return self


class Rule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    intent: str
    when: Condition


MESSAGE_FIELDS = {
    "banking_unavailable": [],
    "invalid_amount": [],
    "quick_transfer_label": [],
    "scan_qr": [],
    "unknown_recipient_label": [],
    "recipient_not_found": ["name"],
    "choose_duplicate_recipient": [],
    "ask_account": [],
    "ask_bank": [],
    "ask_amount": [],
    "minimum_amount": ["minimum"],
    "ask_savings_term": [],
    "unsupported_term": [],
    "insufficient_balance": [],
    "qr_amount_conflict": [],
    "term_detail": ["term_months"],
    "review_summary": ["amount_text", "detail"],
    "unsupported_scenario": [],
    "navigation_opened": [],
    "note_too_long": [],
    "expired": [],
    "cancelled": [],
    "confirm_on_screen": [],
    "editing": [],
    "resume_qr": [],
    "event_cancelled": [],
    "resumed": [],
    "not_qr_flow": [],
    "not_recipient_flow": [],
    "invalid_recipient_query": [],
    "cannot_select_recipient": [],
    "invalid_recipient_choice": [],
    "invalid_qr": [],
    "invalid_qr_information": [],
    "invalid_qr_amount": [],
    "invalid_fields": [],
    "invalid_form_amount": [],
    "invalid_term": [],
    "invalid_note": [],
    "invalid_recipient": [],
    "recipient_account_locked": [],
    "invalid_bank": [],
    "invalid_account": [],
    "review_required": [],
    "risk_updated": [],
    "recipient_name_required": [],
    "account_prepared": [],
    "invalid_preparation_result": [],
    "request_prepared": [],
    "unsupported_event": [],
}


class WorkflowConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal[1]
    ttl_seconds: int = Field(ge=60, le=86400)
    banks: dict[str, list[str]]
    non_action_pattern: str
    scenarios: dict[str, Scenario]
    rules: list[Rule]
    messages: dict[str, str]

    @model_validator(mode="after")
    def validate_references(self):
        re.compile(self.non_action_pattern)
        required = {
            "transfer_account",
            "transfer_recipient",
            "transfer_qr",
            "open_savings",
            "open_loan",
        }
        if not required <= self.scenarios.keys():
            raise ValueError("Missing engine flow definitions")
        if any(self.scenarios[key].kind != "flow" for key in required):
            raise ValueError("Engine flow definitions must have kind=flow")
        if {key for key, value in self.scenarios.items() if value.kind == "flow"} != required:
            raise ValueError("New flow types require an engine handler")
        required_slots = {
            "transfer_account": {"destination.account", "destination.bank", "amount"},
            "transfer_qr": {"qr", "amount"},
            "transfer_recipient": {"amount"},
            "open_savings": {"amount", "term_months"},
            "open_loan": {"amount"},
        }
        for key, slots in required_slots.items():
            configured = [row.slot for row in self.scenarios[key].requirements]
            if set(configured) != slots or len(configured) != len(slots):
                raise ValueError(f"Scenario {key} requires slots {sorted(slots)} exactly once")
        for rule in self.rules:
            if rule.intent not in self.scenarios:
                raise ValueError(f"Unknown intent: {rule.intent}")
        for scenario in self.scenarios.values():
            for requirement in scenario.requirements:
                if requirement.message not in self.messages:
                    raise ValueError(f"Unknown message: {requirement.message}")
                if any(
                    name for _, name, _, _ in Formatter().parse(self.messages[requirement.message])
                ):
                    raise ValueError("Required-slot prompts must not have placeholders")
        for key, expected in MESSAGE_FIELDS.items():
            if key not in self.messages:
                raise ValueError(f"Missing engine message: {key}")
            fields = {
                name for _, name, _, _ in Formatter().parse(self.messages[key]) if name is not None
            }
            if fields != set(expected):
                raise ValueError(f"Message {key} expects placeholders {expected}")
            sample = {
                field: 1 if field in {"minimum", "term_months"} else "sample" for field in expected
            }
            self.messages[key].format(**sample)
        for value in self.messages.values():
            for _, name, _, conversion in Formatter().parse(value):
                if name is not None and (not name.isidentifier() or conversion is not None):
                    raise ValueError("Only named message placeholders are supported")
        return self


def load_workflow_config(path=CONFIG_PATH):
    return WorkflowConfig.model_validate(json.loads(Path(path).read_text(encoding="utf-8")))


CONFIG = load_workflow_config()


def message(key, **values):
    return CONFIG.messages[key].format(**values)
