# Interlocutor Command System — Integration Guide

This is not a drill!

This document describes how to integrate the `interlocutor_commands` module
into the Interlocutor codebase. There are four integration points:

1. **CLI path** — `interlocutor.py`, `TerminalChatInterface._input_loop()`
2. **Web path** — `web_interface.py`, `InterlocutorWebInterface.handle_send_text_message()`
3. **Web UI routing** — `html5_gui/js/websocket.js`, message switch
4. **Web UI rendering** — `html5_gui/js/app.js`, three separate changes

The principle is the same everywhere: **intercept before the chat manager,
display locally, never transmit command results over the air.**

---

## File Placement

Place the `interlocutor_commands/` directory alongside `interlocutor.py`,
parallel to `html5_gui/`:

```
interlocutor/
├── interlocutor.py
├── web_interface.py
├── html5_gui/
│   ├── js/
│   │   ├── app.js
│   │   ├── websocket.js
│   │   └── ...
│   └── ...
├── interlocutor_commands/       ← NEW
│   ├── __init__.py
│   ├── dispatcher.py
│   ├── dice.py
│   └── INTEGRATION.md
├── test_commands.py             ← NEW
├── demo.py                      ← NEW
└── ...
```

No pip install needed. It's a local package import thing!

---

## 1. CLI Integration: interlocutor.py

### Import (add near the top, with other imports)

After the existing imports (around line 90), add:

```python
from interlocutor_commands import dispatcher as command_dispatcher
```

### Patch: TerminalChatInterface._input_loop() (around line 229)

The current flow is:

```
stdin → check "quit" → check "status" → check "clear" → chat_manager.handle_message_input()
```

We insert the command dispatcher check after "clear" and before the
message goes to chat_manager. Find this block (around line 256):

```python
                        if message:
                            # Handle the message through chat manager
                            result = self.chat_manager.handle_message_input(message)
                            self._display_result(result)
```

Replace with:

```python
                        if message:
                            # Check for slash-commands first
                            cmd_result = command_dispatcher.dispatch(message)
                            if cmd_result is not None:
                                # Command recognized — display locally, don't transmit
                                if cmd_result.is_error:
                                    print(f"  ⚠️  {cmd_result.error}")
                                else:
                                    print(f"  {cmd_result.summary}")
                            else:
                                # Normal chat — send through radio pipeline
                                result = self.chat_manager.handle_message_input(message)
                                self._display_result(result)
```

### Add /help to the built-in commands (around line 237)

After the `if message.lower() == 'clear':` block, add:

```python
                        if message.lower() == '/help' or message.lower() == 'help':
                            print("\nAvailable commands:")
                            for name, help_text in command_dispatcher.list_commands():
                                print(f"  {help_text}")
                            print("  status — Show chat statistics")
                            print("  clear  — Clear buffered messages")
                            print("  quit   — Exit chat interface")
                            print()
                            self._show_prompt()
                            continue
```

**Note:** interlocutor.py uses tabs for indentation. The patches above
show spaces for readability — convert to tabs in the actual file.

---

## 2. Web Backend Integration: web_interface.py

### Import (add near the top)

```python
from interlocutor_commands import dispatcher as command_dispatcher
```

### Patch: handle_send_text_message() (around line 330)

The current method receives the message, creates a message_data record,
adds to history, and sends through chat_manager. We intercept at the
very top, before any of that happens.

Find this method:

```python
    async def handle_send_text_message(self, data: Dict):
        """Handle text message from GUI - Enhanced with proper message flow"""
        message = data.get('message', '').strip()
        if not message:
            return
```

Insert the command dispatch check right after the empty check:

```python
    async def handle_send_text_message(self, data: Dict):
        """Handle text message from GUI - Enhanced with proper message flow"""
        message = data.get('message', '').strip()
        if not message:
            return

        # ── Slash-command dispatch ──────────────────────────────
        # Check for commands BEFORE creating message records or
        # sending to chat_manager. Commands are local-only.
        cmd_result = command_dispatcher.dispatch(message)
        if cmd_result is not None:
            # Build a system message for the chat display
            if cmd_result.is_error:
                content = f"⚠️ {cmd_result.error}"
            else:
                content = cmd_result.summary

            command_message = {
                "type": "command_result",
                "direction": "system",
                "content": content,
                "command": cmd_result.command,
                "details": cmd_result.details if not cmd_result.is_error else {},
                "is_error": cmd_result.is_error,
                "timestamp": datetime.now().isoformat(),
                "from": "Interlocutor",
                "message_id": f"cmd_{int(time.time() * 1000)}"
            }

            # Add to history so it persists across reconnects
            self.message_history.append(command_message)

            # Broadcast to all connected web clients
            await self.broadcast_to_all({
                "type": "command_result",
                "data": command_message
            })
            return  # Do NOT send to chat_manager / radio
        # ── End command dispatch ────────────────────────────────

        try:
            # ... existing code continues unchanged ...
```

---

## 3. Web UI Integration: html5_gui/js

There are **four changes** across two JS files. All four are required.

### A. Route command_result messages (websocket.js) — REQUIRED

In `handleWebSocketMessage()` (around line 183), add a case to the
switch statement. Place it before the `default:` case:

```javascript
        case 'command_result':
            handleCommandResult(message.data);
            break;
```

### B. Suppress outgoing bubble for slash-commands (app.js) — REQUIRED

**Why this matters:** `sendMessage()` calls `displayOutgoingMessage()`
immediately, BEFORE the server processes the command. Without this
change, slash-commands appear as blue outgoing text bubbles, then
the command result also appears — you get a duplicate. The raw
command text also incorrectly renders as a sent message.

In `sendMessage()`, find the `displayOutgoingMessage` call:

```javascript
    if (ws && ws.readyState === WebSocket.OPEN) {
        const timestamp = new Date().toISOString();
        displayOutgoingMessage(message, timestamp);
```

Replace with:

```javascript
    if (ws && ws.readyState === WebSocket.OPEN) {
        const timestamp = new Date().toISOString();
        // Don't display slash-commands as outgoing chat — the server
        // will send back a command_result that renders properly
        if (!message.startsWith('/')) {
            displayOutgoingMessage(message, timestamp);
        }
```

### C. Route command results from history (app.js) — REQUIRED

**Why this matters:** When the browser reconnects or refreshes,
`loadMessageHistory()` loads all past messages from the server.
Without this change, command results from history render as
incoming messages (left-aligned, wrong style) instead of centered
system messages. Live results look correct, but refreshing the
page shows them with the wrong styling.

In `loadMessageHistory()`, find the `messages.forEach` loop
(around line 133) and add a type check at the top:

```javascript
    messages.forEach(messageData => {
        // Handle command results from history
        if (messageData.type === 'command_result') {
            handleCommandResult(messageData);
            return;
        }

        let direction = 'incoming';
        let from = messageData.from;
        // ... existing code continues unchanged ...
```

### D. Render command results (app.js) — REQUIRED

Add this function near the other message display functions:

```javascript
// Command result display (dice rolls, etc.)
function handleCommandResult(data) {
    const messageHistory = document.getElementById('message-history');

    const messageEl = document.createElement('div');
    messageEl.className = 'message system command-result';
    messageEl.setAttribute('role', 'log');
    messageEl.setAttribute('aria-live', 'polite');

    const contentEl = document.createElement('div');
    contentEl.className = 'message-content';

    if (data.is_error) {
        contentEl.classList.add('command-error');
        contentEl.textContent = data.content;
    } else {
        contentEl.textContent = data.content;

        // If this is a dice roll, we could add rich rendering here
        // using data.details (rolls array, total, etc.)
        if (data.command === 'roll' && data.details) {
            // Future: animated dice, highlighted crits, etc.
        }
    }

    messageEl.appendChild(contentEl);

    const metaEl = document.createElement('div');
    metaEl.className = 'message-meta';

    const fromEl = document.createElement('span');
    fromEl.className = 'message-from';
    fromEl.textContent = data.from || 'Interlocutor';
    metaEl.appendChild(fromEl);

    const timeEl = document.createElement('span');
    timeEl.className = 'message-time';
    const date = new Date(data.timestamp);
    timeEl.textContent = date.toLocaleTimeString();
    metaEl.appendChild(timeEl);

    messageEl.appendChild(metaEl);
    messageHistory.appendChild(messageEl);
    scrollToBottom(messageHistory);

    announceToScreenReader(`Command result: ${data.content}`);
    addLogEntry(`Command /${data.command}: ${data.content.substring(0, 50)}`, 'info');
}
```

### E. CSS for command results (css/style.css or inline)

```css
/* Command result messages — visually distinct from chat */
/* Centered: neither incoming (left) nor outgoing (right) */
.message.command-result {
    background-color: var(--bg-secondary, #2a2a3e);
    border-left: 3px solid var(--accent-color, #7c6fe0);
    margin: 4px 20%;
    font-family: 'Atkinson Hyperlegible', sans-serif;
}

.message.command-result .message-content {
    font-family: 'Atkinson Hyperlegible Mono', monospace;
    white-space: pre-wrap;
}

.message.command-result .command-error {
    color: var(--error-color, #ff6b6b);
}

.message.command-result .message-from {
    font-style: italic;
    opacity: 0.7;
}
```

### F. Optional: Client-side /help (app.js)

This avoids a server round-trip for the help command. Add this at
the top of `sendMessage()`, before the WebSocket send:

```javascript
    // Client-side /help (no server round-trip needed)
    if (message.toLowerCase() === '/help') {
        handleCommandResult({
            content: 'Available commands:\n' +
                     '  /roll [N]d<S>[+|-<mod>] — Roll dice (e.g., /roll 2d6+3)\n' +
                     '  /r — Shorthand for /roll',
            command: 'help',
            is_error: false,
            from: 'Interlocutor',
            timestamp: new Date().toISOString(),
            details: {}
        });
        messageInput.value = '';
        return;
    }
```

---

## 4. Conference Tab (Future)

When the conference tab is implemented, command results that should
be shared with the party (like dice rolls) will need a separate
broadcast path:

```python
# In the conference handler (future):
if cmd_result is not None and not cmd_result.is_error:
    # Share with conference participants via conference protocol
    await conference.broadcast_event({
        "type": "command_result",
        "command": cmd_result.command,
        "details": cmd_result.details,
        "from": self.station_id,
    })
```

This uses the conference signaling layer, NOT the radio text channel.
Think of it as party chat vs. /say in an MMO — different channels,
different audiences.

---

## Message Flow Summary

### Before integration:
```
User types anything → chat_manager.handle_message_input() → radio TX
```

### After integration:
```
User types "/roll d20"  → dispatcher.dispatch()  → CommandResult → display locally
User types "hello"      → dispatcher returns None → chat_manager   → radio TX
User types "/unknown"   → dispatcher returns None → chat_manager   → radio TX
```

Commands are consumed. Chat passes through. Unknown /commands pass through.
Nothing breaks.

---

## Troubleshooting

### Browser shows blue outgoing bubble for slash-commands
You missed step 3B. The `sendMessage()` function must skip
`displayOutgoingMessage()` for lines starting with `/`.

### Command results render correctly live but wrong after refresh
You missed step 3C. The `loadMessageHistory()` function must
check `messageData.type === 'command_result'` and route those
through `handleCommandResult()` instead of the default renderer.

### Slash-commands show as "Unknown message type" in console
The `command_result` case in `websocket.js` (step 3A) is either
missing or the browser is serving a cached copy of the old file.
See "Browser caching" below.

### Browser caching stale JavaScript files
Safari in particular aggressively caches static JS files served
by FastAPI's StaticFiles. Symptoms: changes to .js files have no
effect, console shows old behavior, server logs show `304 Not Modified`
for JS requests.

Fixes, in order of reliability:
1. **Full browser quit** (Cmd+Q on Mac, not just close window) and
   relaunch. Safari holds cached resources in memory even after
   "Empty Caches" when tabs remain open.
2. **Hard refresh** (Cmd+Shift+R) after emptying caches.
3. **Temporary cache-buster** on script tags in `index.html`:
   `<script src="/static/js/app.js?v=2"></script>`
   Increment the version number on each change. Remove before
   committing.

### CLI works but web interface doesn't
Verify the import in `web_interface.py` (step 2) and that the
`interlocutor_commands/` directory is in the repo root alongside
`web_interface.py`. Python resolves the import relative to the
working directory where you run `interlocutor.py`.

### Indentation errors in interlocutor.py
The codebase uses tabs. Patches in this document show spaces for
readability. Convert to tabs in the actual file.

---

## Testing

Run the test suite:

```bash
cd interlocutor/
python -m pytest test_commands.py -v
```

Manual testing in CLI:

```bash
python interlocutor.py YOUR_CALLSIGN -i 127.0.0.1 --chat-only
# Then type:
/roll d20
/roll 4d6+2
/r d100
/help
hello this is normal chat
the signal/noise ratio is fine
```

The first four should show dice results / help locally. The last two
should go through the normal chat pipeline.

Manual testing in web interface:

```bash
python interlocutor.py YOUR_CALLSIGN -i 127.0.0.1 --web-interface
# Open http://localhost:8000 in browser
```

Verify:
1. `/roll d6` — centered command result, no blue outgoing bubble
2. `/roll fireball damage` — centered error message in red
3. `hello` — blue outgoing bubble on the right (normal chat)
4. Refresh browser — all three should render with same styling
5. `the signal/noise ratio` — normal chat, no command interception
