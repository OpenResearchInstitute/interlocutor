"""
Interlocutor Command System
============================

A slash-command dispatch framework for the Interlocutor human-radio
interface. Provides extensible text commands (gaming, radio, utility)
that work identically in both CLI and web interface contexts.

Architecture Overview
---------------------
The command system sits between user input and the chat manager,
intercepting lines that start with '/' before they reach the
radio transmission pipeline. Think of it as a filter in the
signal chain — commands are consumed locally; everything else
passes through to the air.

    ┌─────────────────┐     ┌──────────────┐     ┌──────────────────────┐
    │  User Input      │────►│  Command     │────►│  ChatManager         │
    │  (CLI or Web)    │     │  Dispatcher  │     │  AudioDriven         │
    └─────────────────┘     └──────┬───────┘     │  → queue_text_message│
                                   │              │  → radio TX pipeline │
                              ┌────▼────┐         └──────────────────────┘
                              │ Command │
                              │ Result  │──► Display locally
                              │ (never  │   (chat window / terminal)
                              │  TX'd)  │
                              └─────────┘

Key design principle: command results are NEVER transmitted over
the air. They are local to the operator's interface. This is the
same as how /roll works in MMOs — your dice result shows in YOUR
chat window (and in a conference context, to your party members
via the conference protocol, not necessarily via the radio link).

Integration Points
------------------
The dispatcher hooks into two places in the Interlocutor codebase:

1. CLI (interlocutor.py, TerminalChatInterface._input_loop):
   Insert dispatch check after the existing "quit"/"status"/"clear"
   checks, before the message reaches chat_manager.handle_message_input().

2. Web (web_interface.py, InterlocutorWebInterface.handle_send_text_message):
   Insert dispatch check at the top of the method, before the message
   reaches self.chat_manager.handle_message_input().

In both cases the pattern is identical:

    from interlocutor_commands import dispatcher

    result = dispatcher.dispatch(user_input)
    if result is not None:
        # Command was recognized — display result locally
        if result.is_error:
            show_error(result.error)
        else:
            show_result(result.summary)
        return  # Do NOT send to chat_manager / radio
    # else: normal chat text, proceed as before

Important! See INTEGRATION.md for the line-by-line patches.

Extending the Command System
-----------------------------
To add a new command:

1. Create a new file in interlocutor_commands/ (e.g., radio.py)
2. Subclass Command from dispatcher.py
3. Implement: name, help_text, execute(args) -> CommandResult
4. Register it in this __init__.py

Example — adding a /freq command, if you can change frequency from
chat in your custom radio integration using Interlocutor. 

    from interlocutor_commands.dispatcher import Command, CommandResult

    class FreqCommand(Command):
        @property
        def name(self) -> str:
            return "freq"

        @property
        def help_text(self) -> str:
            return "/freq <MHz> — Display or set operating frequency"

        def execute(self, args: str) -> CommandResult:
            if not args:
                return CommandResult(
                    command=self.name,
                    summary="Current frequency: 446.000 MHz",
                    details={"frequency": 446.0, "unit": "MHz"}
                )
            # ... parse and validate frequency ...

Then register it:

    from interlocutor_commands.radio import FreqCommand
    dispatcher.register(FreqCommand())

The dispatcher handles all routing. Your command just needs to
parse its own arguments and return a CommandResult.

Module Structure
----------------
    interlocutor_commands/
    ├── __init__.py          ← This file. Builds the default dispatcher.
    ├── dispatcher.py        ← CommandDispatcher, Command ABC, CommandResult.
    │                          The routing layer — like frame sync detection.
    ├── dice.py              ← /roll command. Standard tabletop dice notation.
    │                          First entry in the command spellbook.
    └── (future commands)
        ├── radio.py         ← /freq, /power, /mode — radio control commands
        ├── games.py         ← /coinflip, /draw, /initiative — game utilities
        └── conference.py    ← /who, /mute, /invite — conference management

Protocol Considerations (Conference Tab)
-----------------------------------------
When Interlocutor gains its conference tab, command results may need
to be shared with other conference participants. The CommandResult
structure supports this: the 'details' dict provides structured data
that can be serialized into a conference protocol message, distinct
from normal chat text. This means:

- A /roll result can be broadcast as a "dice_roll" message type
- Other Interlocutor instances can render it with appropriate UI
  (animated dice, color-coded crits, etc.)
- The result is never sent through the radio modem's text channel —
  it travels through the conference signaling layer instead. Sneaky!

This mirrors how MMO chat channels work as best we can
/roll results go to partychat, not to /say (local area).

Dependencies
------------
Standard library only. No external packages required.
Uses: re, random, abc, dataclasses, typing.

License
-------
GPL 3.0

"""

from interlocutor_commands.dispatcher import CommandDispatcher, CommandResult
from interlocutor_commands.dice import DiceCommand

# ─── Build the default dispatcher with all registered commands ──────

dispatcher = CommandDispatcher()
dispatcher.register(DiceCommand())

# Future registrations:
# from interlocutor_commands.radio import FreqCommand, PowerCommand
# dispatcher.register(FreqCommand())
# dispatcher.register(PowerCommand())

__all__ = ['dispatcher', 'CommandDispatcher', 'CommandResult']
