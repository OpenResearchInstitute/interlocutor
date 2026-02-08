"""
Command Dispatcher
==================

The central routing table for Interlocutor slash-commands.

Role in the System
------------------
This module is analogous to frame sync detection in the modem. 
It examines the preamble of each chat line and routes to the
appropriate handler. If the preamble doesn't match any registered
command, it returns None, signaling that the line is normal chat
text and should proceed to ChatManagerAudioDriven for radio
transmission.

    User types: "/roll 2d6+3"
                  ↓
    Dispatcher sees "/" prefix → splits "roll" + "2d6+3"
                  ↓
    Looks up "roll" in command registry → found!
                  ↓
    Calls DiceCommand.execute("2d6+3") → CommandResult
                  ↓
    Returns result to caller (CLI or web handler)

    User types: "Hello everyone"
                  ↓
    Dispatcher sees no "/" prefix → returns None
                  ↓
    Caller sends to chat_manager.handle_message_input() as usual

Design Decisions
----------------
- Commands are case-insensitive (/Roll, /ROLL, /roll all work).
- Only lines starting with / are candidates. A / mid-sentence
  (e.g., "signal/noise") is never misidentified as a command.
- Unrecognized commands (e.g., "/foo") return None, not an error.
  This is intentional: future versions might add commands, and we
  don't want to block text that happens to start with "/".
  If you want strict mode (error on unknown /commands), that's a
  one-line change in dispatch().
- Each command owns its own argument parsing and validation.
  The dispatcher only handles routing.
- Results are structured (CommandResult) so the UI layer can
  render them appropriately. Summary text for CLI, structured
  data dict for web UI rich rendering.

Classes
-------
CommandResult
    Structured output from any command execution. Contains:
    - command: which command produced this (for UI routing)
    - summary: human-readable one-liner (CLI display)
    - details: structured dict (web UI rich rendering)
    - error: if set, the command was recognized but input was invalid

Command (ABC)
    Base class for all command handlers. Subclass to add commands.
    Required: name, help_text, execute(args).
    Optional: aliases (e.g., /r as shorthand for /roll).

CommandDispatcher
    The registry and router. Register Command instances, then call
    dispatch(line) on each chat input line.

Extending
---------
See __init__.py docstring for the full extension guide. Quick version:

    class MyCommand(Command):
        @property
        def name(self) -> str: return "mycommand"

        @property
        def help_text(self) -> str: return "/mycommand — Does a thing"

        def execute(self, args: str) -> CommandResult:
            return CommandResult(command=self.name, summary="Did the thing!")

    dispatcher.register(MyCommand())
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CommandResult:
    """Structured output from a command execution.

    This is the "demodulated frame" of the command system — the
    parsed, processed result ready for display.

    Attributes
    ----------
    command : str
        The command name that produced this result (e.g., "roll").
        Used by the UI layer to select the appropriate renderer.

    summary : str
        Human-readable one-line summary for display.
        This is what the CLI prints and what simple UIs show.
        Examples:
            "2d6+3 → [4, 5] + 3 = 12"
            "Frequency set to 446.000 MHz"

    details : dict
        Structured data for rich UI rendering. The web interface
        can use this to show animated dice, frequency displays,
        card graphics, etc. Each command defines its own schema.
        For dice: {"rolls": [4, 5], "modifier": 3, "total": 12, ...}
        For radio: {"frequency": 446.0, "unit": "MHz", ...}

    error : str or None
        If set, the command recognized the input but couldn't
        execute it. Contains a user-friendly error message.
        The summary field is ignored when error is set.
    """
    command: str
    summary: str
    details: dict = field(default_factory=dict)
    error: Optional[str] = None

    @property
    def is_error(self) -> bool:
        """Check if this result represents an error."""
        return self.error is not None


class Command(ABC):
    """Base class for all Interlocutor commands.

    Subclass this to add a new slash-command. Think of each
    Command subclass as a spell in Interlocutor's spellbook —
    the Dispatcher is the casting mechanism that routes the
    incantation to the right spell.

    Required Properties
    -------------------
    name : str
        Primary command keyword (lowercase, no slash).
        This is what the user types after '/'.

    help_text : str
        One-line description shown in /help listings.
        Convention: "/name <args> — Description"

    Required Methods
    ----------------
    execute(args: str) -> CommandResult
        Parse the argument string and execute the command.
        The args parameter is everything after the command name,
        stripped of leading whitespace.

    Optional Properties
    -------------------
    aliases : list[str]
        Alternative names that also trigger this command.
        Example: ["r"] so /r works as shorthand for /roll.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Primary command name (lowercase, no slash)."""
        ...

    @property
    def aliases(self) -> list[str]:
        """Alternative names that also trigger this command."""
        return []

    @property
    @abstractmethod
    def help_text(self) -> str:
        """One-line usage description for /help listings."""
        ...

    @abstractmethod
    def execute(self, args: str) -> CommandResult:
        """Parse arguments and execute the command.

        Parameters
        ----------
        args : str
            Everything after the command name, stripped of leading
            whitespace. For "/roll 2d6+3", args is "2d6+3".
            For "/roll" with no args, args is "".

        Returns
        -------
        CommandResult
            Always returns a result — either successful (summary + details)
            or an error (error message with usage hint).
            Never returns None; never raises exceptions to the caller.
        """
        ...


class CommandDispatcher:
    """Routes chat lines to registered command handlers.

    This is the command registry and router. It maintains a dict
    mapping command names (and aliases) to Command handler instances.

    Thread Safety
    -------------
    The dispatch() method is read-only after initialization and is
    safe to call from multiple threads (CLI input thread, web async
    handlers, etc.). Registration should happen at startup before
    any dispatching begins.

    Usage
    -----
        dispatcher = CommandDispatcher()
        dispatcher.register(DiceCommand())
        dispatcher.register(FreqCommand())

        # In your input handler:
        result = dispatcher.dispatch(user_input)
        if result is not None:
            display(result)  # it was a command
        else:
            send_to_radio(user_input)  # normal chat
    """

    def __init__(self):
        self._commands: dict[str, Command] = {}

    def register(self, command: Command) -> None:
        """Register a command handler.

        Parameters
        ----------
        command : Command
            The command handler instance to register.

        Raises
        ------
        ValueError
            If the command name or any alias collides with an
            already-registered name.
        """
        for key in [command.name] + command.aliases:
            key = key.lower()
            if key in self._commands:
                raise ValueError(
                    f"Command name collision: '{key}' is already registered "
                    f"to '{self._commands[key].name}'"
                )
            self._commands[key] = command

    def dispatch(self, line: str) -> Optional[CommandResult]:
        """Attempt to dispatch a chat line as a command.

        This is the main entry point. Call it on every line of
        chat input. It returns quickly for non-command lines
        (just a startswith check).

        Parameters
        ----------
        line : str
            A single line of chat input from the user.

        Returns
        -------
        CommandResult or None
            CommandResult if the line matched a registered command.
            None if the line is normal chat text (no '/' prefix,
            or unrecognized command name).

        Note
        ----
        Unrecognized /commands return None, not an error. This means
        a line like "/frequency 446" won't be blocked if the freq
        command isn't registered yet — it will pass through as chat.
        """
        stripped = line.strip()

        # Only lines starting with / are command candidates
        if not stripped.startswith('/'):
            return None

        # Split into command name and arguments
        without_slash = stripped[1:]
        parts = without_slash.split(None, 1)  # split on first whitespace
        if not parts:
            return None

        cmd_name = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        # Look up the handler
        command = self._commands.get(cmd_name)
        if command is None:
            return None  # Unrecognized → treat as normal chat

        return command.execute(args)

    def list_commands(self) -> list[tuple[str, str]]:
        """Return (name, help_text) for all registered commands.

        Deduplicates aliases so each command appears once.
        Sorted alphabetically by name.
        """
        seen = set()
        result = []
        for cmd in self._commands.values():
            if cmd.name not in seen:
                seen.add(cmd.name)
                result.append((cmd.name, cmd.help_text))
        return sorted(result, key=lambda x: x[0])
