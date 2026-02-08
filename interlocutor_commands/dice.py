"""
Dice Command (/roll)
====================

Implements tabletop RPG dice rolling using standard dice notation.
This is the first entry in Interlocutor's command spellbook.

Dice Notation Grammar
---------------------
The grammar follows the universal tabletop standard:

    /roll [N]d<S>[+|-<modifier>]

    N         Number of dice to roll (default: 1, max: 100)
    d         Literal 'd' (case-insensitive)
    S         Number of sides per die (min: 2, max: 1000)
    modifier  Integer added to or subtracted from the total

The parser is whitespace-tolerant around the modifier operator,
so all of these are equivalent:

    /roll d10+7
    /roll d10 + 7
    /roll d10 +7

Examples
--------
    /roll d20          →  🎲 d20 → [14] = 14
    /roll 4d6          →  🎲 4d6 → [3, 5, 1, 6] = 15
    /roll 2d8+5        →  🎲 2d8+5 → [7, 3] + 5 = 15
    /roll d100         →  🎲 d100 → [73] = 73
    /roll 3d6-2        →  🎲 3d6-2 → [4, 2, 6] - 2 = 10

    /r d20             →  Same as /roll d20 (alias)

Aliases
-------
    /r  — Quick alias for frequent rollers. Because when
          initiative is on the line, every keystroke counts.

Design: Domain Model
--------------------
The dice system uses three domain objects that separate concerns
cleanly — the same principle as separating frame format from
modulation from transmission in the modem stack:

    DiceExpression  →  The parsed "what to roll" (like a frame header)
    DiceResult      →  The outcome with individual rolls (like demodulated data)
    DiceCommand     →  The Command handler that ties it together

DiceExpression is a frozen dataclass — immutable once parsed.
DiceResult stores individual roll values for transparency
(no fudging allowed, and some D&D mechanics need individual
die values, like dropping the lowest on ability score rolls).

Limits and Guardrails
---------------------
    Max dice per roll:  100  (prevents chat spam / overflow)
    Min sides:            2  (a d1 isn't a die, it's a bead)
    Max sides:         1000  (a d1000 would take forever to stop)
    Max modifier:    10000   (even epic-level bonuses have limits)

These are enforced in parse_dice() with friendly error messages.

Random Number Generation
------------------------
Uses Python's random.randint() (Mersenne Twister PRNG), which is
perfectly adequate for gaming. If we ever need cryptographic fairness
for over-the-air competitive rolls in the conference system, we can
swap in secrets.randbelow() — the RNG is isolated in roll_dice().

Output Format
-------------
The summary format shows individual rolls for transparency:

    🎲 <expression> → [<rolls>] [+|- <mod>] = <total>

The details dict provides structured data for rich UI rendering:

    {
        "expression": "2d6+3",
        "count": 2,
        "sides": 6,
        "modifier": 3,
        "rolls": [4, 5],
        "subtotal": 9,
        "total": 12
    }

The web UI can use this to render animated dice, highlight
natural 20s, show crits in red, etc.

Future Extensions
-----------------
The grammar can grow to support advanced notation without
breaking existing rolls. Planned suffixes:

    4d6kh3     Keep highest 3 (classic ability score method)
    2d20kh1    Keep highest 1 (D&D 5e advantage)
    2d20kl1    Keep lowest 1 (D&D 5e disadvantage)
    4d6!       Exploding dice (reroll on max, add)
    8d10t6     Target number (count successes >= 6, WoD style)

These would be added as optional fields on DiceExpression.
The regex would gain optional suffix groups. Existing notation
continues to parse unchanged.

Module Contents
---------------
    DiceExpression   Frozen dataclass: parsed dice notation
    DiceResult       Frozen dataclass: roll outcome with details
    parse_dice()     Notation string → DiceExpression (or None/ValueError)
    roll_dice()      DiceExpression → DiceResult
    DiceCommand      The Command handler registered as /roll
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass
from typing import Optional

from interlocutor_commands.dispatcher import Command, CommandResult


# ─── Domain Model ───────────────────────────────────────────────────

@dataclass(frozen=True)
class DiceExpression:
    """A parsed dice notation expression.

    This is the "frame format" for a dice roll request —
    structured data extracted from the user's text input.
    Immutable once created (frozen=True).

    Attributes
    ----------
    count : int
        Number of dice to roll (1-100).
    sides : int
        Number of faces per die (2-1000).
    modifier : int
        Integer added to total. Negative for subtraction.
    """
    count: int       # number of dice
    sides: int       # faces per die
    modifier: int    # added to total (can be negative)

    def __str__(self) -> str:
        """Reconstruct canonical dice notation string.

        Single die omits the count: "d20" not "1d20".
        Negative modifiers include the minus: "d20-3".
        """
        base = f"{self.count}d{self.sides}" if self.count > 1 else f"d{self.sides}"
        if self.modifier > 0:
            return f"{base}+{self.modifier}"
        elif self.modifier < 0:
            return f"{base}{self.modifier}"  # minus sign is part of the int
        return base


@dataclass(frozen=True)
class DiceResult:
    """The outcome of rolling a DiceExpression.

    Stores individual roll values for transparency and for
    game mechanics that need them (drop lowest, count successes, etc.).

    Attributes
    ----------
    expression : DiceExpression
        The original roll request (for display formatting).
    rolls : tuple[int, ...]
        Individual die results. Tuple (not list) for immutability.
    total : int
        Final result: sum(rolls) + expression.modifier.
    """
    expression: DiceExpression
    rolls: tuple[int, ...]
    total: int

    @property
    def subtotal(self) -> int:
        """Sum of just the dice, before modifier."""
        return sum(self.rolls)

    def format_summary(self) -> str:
        """Human-readable one-line summary.

        Format: 🎲 <notation> → [<rolls>] [+|- <mod>] = <total>

        Examples:
            🎲 d20 → [14] = 14
            🎲 4d6+2 → [3, 5, 1, 6] + 2 = 17
            🎲 2d8-1 → [7, 3] - 1 = 9
        """
        rolls_str = ", ".join(str(r) for r in self.rolls)
        expr_str = str(self.expression)
        mod = self.expression.modifier

        if mod > 0:
            return f"\U0001f3b2 {expr_str} \u2192 [{rolls_str}] + {mod} = {self.total}"
        elif mod < 0:
            return f"\U0001f3b2 {expr_str} \u2192 [{rolls_str}] - {abs(mod)} = {self.total}"
        else:
            return f"\U0001f3b2 {expr_str} \u2192 [{rolls_str}] = {self.total}"

    def to_dict(self) -> dict:
        """Structured data for rich UI rendering.

        Returns a dict suitable for JSON serialization and
        WebSocket transmission to the web interface.
        """
        return {
            "expression": str(self.expression),
            "count": self.expression.count,
            "sides": self.expression.sides,
            "modifier": self.expression.modifier,
            "rolls": list(self.rolls),
            "subtotal": self.subtotal,
            "total": self.total,
        }


# ─── Parser ─────────────────────────────────────────────────────────

# Regex for standard dice notation.
# Whitespace around the modifier operator is tolerated.
# Groups: (count)(sides)(operator)(modifier_value)
_DICE_PATTERN = re.compile(
    r'^(\d*)d(\d+)(?:\s*([+-])\s*(\d+))?$',
    re.IGNORECASE
)

# Guardrails — the boundaries of the known multiverse
MAX_DICE = 100
MIN_SIDES = 2
MAX_SIDES = 1000
MAX_MODIFIER = 10000


def parse_dice(notation: str) -> Optional[DiceExpression]:
    """Parse a dice notation string into a DiceExpression.

    Parameters
    ----------
    notation : str
        The argument string after '/roll', e.g. "2d6+3" or "d20".

    Returns
    -------
    DiceExpression or None
        DiceExpression if the notation matches the grammar.
        None if the notation doesn't match at all (not dice notation).

    Raises
    ------
    ValueError
        If the notation matches the grammar but violates limits
        (too many dice, invalid sides, excessive modifier).
        Error messages include flavor text because life is short.
    """
    notation = notation.strip()
    match = _DICE_PATTERN.match(notation)
    if match is None:
        return None

    count_str, sides_str, operator, mod_str = match.groups()

    count = int(count_str) if count_str else 1
    sides = int(sides_str)
    modifier = 0

    if operator and mod_str:
        modifier = int(mod_str)
        if operator == '-':
            modifier = -modifier

    # Validate limits
    if count < 1 or count > MAX_DICE:
        raise ValueError(
            f"Dice count must be between 1 and {MAX_DICE}, got {count}. "
            f"Even Tiamat doesn't roll that many dice."
        )

    if sides < MIN_SIDES or sides > MAX_SIDES:
        raise ValueError(
            f"Die sides must be between {MIN_SIDES} and {MAX_SIDES}, got {sides}. "
            f"A d1 is just a bead, and a d{sides} would take forever to stop rolling."
        )

    if abs(modifier) > MAX_MODIFIER:
        raise ValueError(
            f"Modifier must be between -{MAX_MODIFIER} and +{MAX_MODIFIER}. "
            f"That's beyond even epic-level bonuses."
        )

    return DiceExpression(count=count, sides=sides, modifier=modifier)


# ─── Roller ─────────────────────────────────────────────────────────

def roll_dice(expression: DiceExpression) -> DiceResult:
    """Roll the dice defined by a DiceExpression.

    Parameters
    ----------
    expression : DiceExpression
        What to roll.

    Returns
    -------
    DiceResult
        The outcome, including individual roll values.

    Notes
    -----
    Uses random.randint() (Mersenne Twister). Adequate for gaming.
    For cryptographic fairness in competitive over-the-air rolls,
    replace with secrets.randbelow(sides) + 1.
    """
    rolls = tuple(random.randint(1, expression.sides) for _ in range(expression.count))
    total = sum(rolls) + expression.modifier
    return DiceResult(expression=expression, rolls=rolls, total=total)


# ─── Command Handler ────────────────────────────────────────────────

class DiceCommand(Command):
    """The /roll command for tabletop dice rolling.

    First entry in Interlocutor's command spellbook.
    Registered as both /roll and /r.
    """

    @property
    def name(self) -> str:
        return "roll"

    @property
    def aliases(self) -> list[str]:
        return ["r"]  # /r d20 for the impatient

    @property
    def help_text(self) -> str:
        return "/roll [N]d<S>[+|-<mod>] \u2014 Roll dice (e.g., /roll 2d6+3)"

    def execute(self, args: str) -> CommandResult:
        """Parse dice notation and roll.

        Returns CommandResult with summary and structured details.
        On invalid input, returns CommandResult with error set.
        """
        if not args.strip():
            return CommandResult(
                command=self.name,
                summary="",
                error="No dice notation provided. Usage: /roll [N]d<S>[+|-<mod>]\n"
                       "Examples: /roll d20, /roll 4d6, /roll 2d8+5"
            )

        try:
            expression = parse_dice(args)
        except ValueError as e:
            return CommandResult(
                command=self.name,
                summary="",
                error=str(e)
            )

        if expression is None:
            return CommandResult(
                command=self.name,
                summary="",
                error=f"Could not parse dice notation: '{args}'\n"
                       f"Expected format: [N]d<S>[+|-<mod>] (e.g., 2d6+3, d20, 4d6-1)"
            )

        result = roll_dice(expression)

        return CommandResult(
            command=self.name,
            summary=result.format_summary(),
            details=result.to_dict()
        )
