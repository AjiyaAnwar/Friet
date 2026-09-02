"""Rules engine unit tests."""

from app.modules.rules.service import RuleCondition, RuleConditionGroup, RulesEngine


class DummySession:
    async def execute(self, *args, **kwargs):
        class Result:
            def all(self):
                return []

        return Result()

    def add(self, obj):
        pass


def test_rules_and_or():
    engine = RulesEngine(DummySession())  # type: ignore[arg-type]
    group = RuleConditionGroup(
        combinator="AND",
        conditions=[
            RuleCondition(field="margin_pct", operator="gte", value=10),
            RuleCondition(field="tier", operator="eq", value="A"),
        ],
    )
    assert engine.evaluate_conditions(group, {"margin_pct": 12, "tier": "A"})
    assert not engine.evaluate_conditions(group, {"margin_pct": 5, "tier": "A"})


def test_rules_or_combinator():
    engine = RulesEngine(DummySession())  # type: ignore[arg-type]
    group = RuleConditionGroup(
        combinator="OR",
        conditions=[
            RuleCondition(field="dgr", operator="eq", value=True),
            RuleCondition(field="value", operator="gt", value=100000),
        ],
    )
    assert engine.evaluate_conditions(group, {"dgr": False, "value": 200000})
