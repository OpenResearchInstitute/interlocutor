#!/usr/bin/env python3
"""
Interlocutor Command System — Interactive Demo

This simulates the chat input loop. Type normal chat text or
use slash-commands. Try:

    /roll d20
    /roll 4d6+2
    /r d10 - 3
    /help
    hello this is normal chat
    the signal/noise ratio is fine
    /quit

"""

from interlocutor_commands import dispatcher


def main():
    print("=" * 60)
    print("  Interlocutor Command System — Demo")
    print("  Type /help for commands, /quit to exit")
    print("=" * 60)
    print()

    while True:
        try:
            line = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n73!")
            break

        if not line:
            continue

        if line.lower() == "/quit":
            print("73!")
            break

        if line.lower() == "/help":
            print("\nAvailable commands:")
            for name, help_text in dispatcher.list_commands():
                print(f"  {help_text}")
            print()
            continue

        # Try dispatching as a command
        result = dispatcher.dispatch(line)

        if result is None:
            # Not a command — in real Interlocutor this goes to the chat stream
            print(f"  [chat] {line}")
        elif result.is_error:
            print(f"  [error] {result.error}")
        else:
            print(f"  {result.summary}")


if __name__ == "__main__":
    main()
