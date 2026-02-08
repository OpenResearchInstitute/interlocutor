"""
Tests for the Interlocutor command system.

Run with:  python -m pytest test_commands.py -v
"""

import pytest

from interlocutor_commands.dispatcher import CommandDispatcher, CommandResult
from interlocutor_commands.dice import (
    DiceCommand,
    DiceExpression,
    DiceResult,
    parse_dice,
    roll_dice,
)
from interlocutor_commands import dispatcher as default_dispatcher


# ============================================================
# DiceExpression parsing
# ============================================================

class TestParseDice:
    """Tests for the dice notation parser."""

    def test_simple_d20(self):
        expr = parse_dice("d20")
        assert expr == DiceExpression(count=1, sides=20, modifier=0)

    def test_multiple_dice(self):
        expr = parse_dice("4d6")
        assert expr == DiceExpression(count=4, sides=6, modifier=0)

    def test_positive_modifier(self):
        expr = parse_dice("2d8+5")
        assert expr == DiceExpression(count=2, sides=8, modifier=5)

    def test_negative_modifier(self):
        expr = parse_dice("3d6-2")
        assert expr == DiceExpression(count=3, sides=6, modifier=-2)

    def test_whitespace_around_modifier(self):
        expr = parse_dice("d10 + 7")
        assert expr == DiceExpression(count=1, sides=10, modifier=7)

    def test_whitespace_negative_modifier(self):
        expr = parse_dice("2d6 - 3")
        assert expr == DiceExpression(count=2, sides=6, modifier=-3)

    def test_percentile_die(self):
        expr = parse_dice("d100")
        assert expr == DiceExpression(count=1, sides=100, modifier=0)

    def test_case_insensitive(self):
        expr = parse_dice("D20")
        assert expr == DiceExpression(count=1, sides=20, modifier=0)

    def test_leading_trailing_whitespace(self):
        expr = parse_dice("  2d6+1  ")
        assert expr == DiceExpression(count=2, sides=6, modifier=1)

    def test_invalid_notation_returns_none(self):
        assert parse_dice("hello") is None
        assert parse_dice("d") is None
        assert parse_dice("20") is None
        assert parse_dice("roll d20") is None  # no slash, but also no dice-only
        assert parse_dice("") is None

    def test_too_many_dice_raises(self):
        with pytest.raises(ValueError, match="Dice count"):
            parse_dice("200d6")

    def test_zero_dice_raises(self):
        with pytest.raises(ValueError, match="Dice count"):
            parse_dice("0d6")

    def test_d1_raises(self):
        with pytest.raises(ValueError, match="Die sides"):
            parse_dice("d1")

    def test_excessive_sides_raises(self):
        with pytest.raises(ValueError, match="Die sides"):
            parse_dice("d9999")

    def test_excessive_modifier_raises(self):
        with pytest.raises(ValueError, match="Modifier"):
            parse_dice("d20+99999")


class TestDiceExpressionStr:
    """Tests for canonical string reconstruction."""

    def test_single_die(self):
        assert str(DiceExpression(1, 20, 0)) == "d20"

    def test_multiple_dice(self):
        assert str(DiceExpression(4, 6, 0)) == "4d6"

    def test_positive_modifier(self):
        assert str(DiceExpression(2, 8, 5)) == "2d8+5"

    def test_negative_modifier(self):
        assert str(DiceExpression(1, 10, -3)) == "d10-3"


# ============================================================
# Rolling
# ============================================================

class TestRollDice:
    """Tests for the dice roller."""

    def test_roll_produces_correct_count(self):
        expr = DiceExpression(count=5, sides=6, modifier=0)
        result = roll_dice(expr)
        assert len(result.rolls) == 5

    def test_all_rolls_within_range(self):
        expr = DiceExpression(count=50, sides=20, modifier=0)
        result = roll_dice(expr)
        assert all(1 <= r <= 20 for r in result.rolls)

    def test_modifier_applied_to_total(self):
        expr = DiceExpression(count=1, sides=6, modifier=10)
        result = roll_dice(expr)
        assert result.total == result.rolls[0] + 10

    def test_negative_modifier(self):
        expr = DiceExpression(count=1, sides=6, modifier=-3)
        result = roll_dice(expr)
        assert result.total == result.rolls[0] - 3

    def test_subtotal_is_sum_of_rolls(self):
        expr = DiceExpression(count=4, sides=6, modifier=5)
        result = roll_dice(expr)
        assert result.subtotal == sum(result.rolls)
        assert result.total == result.subtotal + 5

    def test_result_to_dict(self):
        expr = DiceExpression(count=2, sides=8, modifier=3)
        result = roll_dice(expr)
        d = result.to_dict()
        assert d["count"] == 2
        assert d["sides"] == 8
        assert d["modifier"] == 3
        assert len(d["rolls"]) == 2
        assert d["total"] == sum(d["rolls"]) + 3


class TestDiceResultFormat:
    """Tests for human-readable output formatting."""

    def test_no_modifier_format(self):
        result = DiceResult(
            expression=DiceExpression(1, 20, 0),
            rolls=(14,),
            total=14,
        )
        summary = result.format_summary()
        assert "d20" in summary
        assert "[14]" in summary
        assert "= 14" in summary

    def test_positive_modifier_format(self):
        result = DiceResult(
            expression=DiceExpression(2, 6, 3),
            rolls=(4, 5),
            total=12,
        )
        summary = result.format_summary()
        assert "2d6+3" in summary
        assert "[4, 5]" in summary
        assert "+ 3" in summary
        assert "= 12" in summary

    def test_negative_modifier_format(self):
        result = DiceResult(
            expression=DiceExpression(1, 8, -2),
            rolls=(6,),
            total=4,
        )
        summary = result.format_summary()
        assert "d8-2" in summary
        assert "- 2" in summary
        assert "= 4" in summary


# ============================================================
# Command dispatch
# ============================================================

class TestDispatcher:
    """Tests for the command routing layer."""

    def test_non_command_returns_none(self):
        result = default_dispatcher.dispatch("hello everyone")
        assert result is None

    def test_slash_in_middle_returns_none(self):
        result = default_dispatcher.dispatch("the signal/noise ratio is good")
        assert result is None

    def test_unknown_command_returns_none(self):
        result = default_dispatcher.dispatch("/unknown 42")
        assert result is None

    def test_roll_command_works(self):
        result = default_dispatcher.dispatch("/roll d20")
        assert result is not None
        assert result.command == "roll"
        assert not result.is_error

    def test_roll_alias_works(self):
        result = default_dispatcher.dispatch("/r d20")
        assert result is not None
        assert result.command == "roll"

    def test_case_insensitive_command(self):
        result = default_dispatcher.dispatch("/Roll 2d6")
        assert result is not None
        assert not result.is_error

    def test_roll_with_full_notation(self):
        result = default_dispatcher.dispatch("/roll 4d6+2")
        assert result is not None
        assert result.details["count"] == 4
        assert result.details["sides"] == 6
        assert result.details["modifier"] == 2

    def test_roll_no_args_gives_error(self):
        result = default_dispatcher.dispatch("/roll")
        assert result is not None
        assert result.is_error
        assert "Usage" in result.error

    def test_roll_bad_notation_gives_error(self):
        result = default_dispatcher.dispatch("/roll banana")
        assert result is not None
        assert result.is_error

    def test_list_commands(self):
        cmds = default_dispatcher.list_commands()
        names = [name for name, _ in cmds]
        assert "roll" in names

    def test_register_collision_raises(self):
        d = CommandDispatcher()
        d.register(DiceCommand())
        with pytest.raises(ValueError, match="collision"):
            d.register(DiceCommand())  # same name again


# ============================================================
# Integration: edge cases that cross layers
# ============================================================

class TestIntegration:
    """End-to-end tests through the full dispatch pipeline."""

    def test_d100_percentile(self):
        result = default_dispatcher.dispatch("/roll d100")
        assert 1 <= result.details["total"] <= 100

    def test_max_dice(self):
        result = default_dispatcher.dispatch("/roll 100d6")
        assert len(result.details["rolls"]) == 100

    def test_over_max_dice_error(self):
        result = default_dispatcher.dispatch("/roll 101d6")
        assert result.is_error

    def test_whitespace_tolerance(self):
        result = default_dispatcher.dispatch("/roll  d10 + 5 ")
        assert result is not None
        assert not result.is_error
        assert result.details["modifier"] == 5
