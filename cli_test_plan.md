# Interlocutor CLI Testing Plan

Test like a radio operator: start simple, add complexity, verify every control works as expected.

## **Pre-Test Setup**
Before each test session, establish known states:

### Clean Slate Tests (simulate new user)
```bash
# Remove all config files
rm -f *.yaml audio_config.yaml

# Verify clean state
ls -la *.yaml  # Should show "No such file"
```

### Known State Tests (simulate returning user)
```bash
# Ensure config files exist with known good settings
cp test_configs/good_config.yaml opulent_voice_config.yaml
cp test_configs/good_audio.yaml audio_config.yaml
```

## 🧪 **Test Cases**

### **Phase 1: Basic Operation**
| Test | Command | Expected Result | Pass/Fail | Notes |
|------|---------|----------------|-----------|-------|
| Default run | `python radio.py W1ABC` | Starts normally, uses defaults | ⬜ | |
| Help display | `python radio.py --help` | Shows all options clearly | ⬜ | |
| Version info | `python radio.py --version` | Shows version, exits cleanly | ⬜ | |
| Bad callsign | `python radio.py "BAD CALL!"` | Clear error message | ⬜ | |
| No callsign | `python radio.py` | Usage message | ⬜ | |

### **Phase 2: Audio Device Options**
| Test | Command | Expected Result | Pass/Fail | Notes |
|------|---------|----------------|-----------|-------|
| List devices | `python radio.py W1ABC --list-audio` | Shows devices, exits | ⬜ | |
| Force setup | `python radio.py W1ABC --setup-audio` | Interactive selection | ⬜ | |
| Test audio | `python radio.py W1ABC --test-audio` | Tests current devices | ⬜ | |
| Setup + verbose | `python radio.py W1ABC --setup-audio -v` | Detailed device info | ⬜ | |

### **Phase 3: Network Configuration**
| Test | Command | Expected Result | Pass/Fail | Notes |
|------|---------|----------------|-----------|-------|
| Custom IP | `python radio.py W1ABC -i 192.168.5.100` | Uses specified IP | ⬜ | |
| Custom port | `python radio.py W1ABC -p 12345` | Uses specified port | ⬜ | |
| Both custom | `python radio.py W1ABC -i 10.0.0.50 -p 9999` | Uses both settings | ⬜ | |
| Invalid IP | `python radio.py W1ABC -i 999.999.999.999` | Error handling | ⬜ | |
| Invalid port | `python radio.py W1ABC -p 99999` | Error handling | ⬜ | |

### **Phase 4: Operating Modes**
| Test | Command | Expected Result | Pass/Fail | Notes |
|------|---------|----------------|-----------|-------|
| Chat only | `python radio.py W1ABC --chat-only` | No GPIO/audio setup | ⬜ | |
| Verbose mode | `python radio.py W1ABC -v` | Debug output shown | ⬜ | |
| Quiet mode | `python radio.py W1ABC -q` | Minimal output | ⬜ | |
| Verbose + quiet | `python radio.py W1ABC -v -q` | Conflict handling | ⬜ | |

### **Phase 5: Configuration Files**
| Test | Command | Expected Result | Pass/Fail | Notes |
|------|---------|----------------|-----------|-------|
| No config files | `python radio.py W1ABC` | Creates defaults | ⬜ | |
| Partial config | `python radio.py W1ABC` | Fills missing values | ⬜ | |
| Corrupted config | `python radio.py W1ABC` | Handles gracefully | ⬜ | |
| Custom config | `python radio.py W1ABC -c my_config.yaml` | Uses specified file | ⬜ | |

### **Phase 6: Edge Cases & Error Handling**
| Test | Command | Expected Result | Pass/Fail | Notes |
|------|---------|----------------|-----------|-------|
| No permissions | `sudo chown root:root .` then test | Clear error message | ⬜ | |
| No virtual env | Test outside venv | Virtual env warning | ⬜ | |
| Missing dependencies | Rename opuslib | Clear install instructions | ⬜ | |
| Ctrl+C during setup | Interrupt during audio setup | Clean shutdown | ⬜ | |
| Invalid GPIO pins | Set impossible pin numbers | Clear error | ⬜ | |

### **Phase 7: Real-World Scenarios**
| Test | Command | Expected Result | Pass/Fail | Notes |
|------|---------|----------------|-----------|-------|
| First-time user | Fresh Pi, no configs | Guided setup works | ⬜ | |
| Headset swap | `--setup-audio` with new USB device | Detects new device | ⬜ | |
| Network change | Change IP, restart | Picks up new IP | ⬜ | |
| Long session | Run for 30+ minutes | Stable operation | ⬜ | |
| Multiple restarts | Start/stop 10 times | Consistent behavior | ⬜ | |

## **Automated Test Script**

Create `test_cli.sh` for systematic testing:

```bash
#!/bin/bash
# Opulent Voice CLI Test Runner

echo "🧪 Starting CLI test suite..."

# Test counter
TESTS=0
PASSED=0
FAILED=0

# Function to run a test
run_test() {
    local test_name="$1"
    local command="$2"
    local expected_exit="$3"
    
    echo "Testing: $test_name"
    echo "Command: $command"
    
    TESTS=$((TESTS + 1))
    
    # Run command with timeout
    timeout 10s bash -c "$command" >/dev/null 2>&1
    exit_code=$?
    
    if [ $exit_code -eq $expected_exit ]; then
        echo "✅ PASS"
        PASSED=$((PASSED + 1))
    else
        echo "❌ FAIL (exit code: $exit_code, expected: $expected_exit)"
        FAILED=$((FAILED + 1))
    fi
    echo
}

# Clean slate
rm -f *.yaml 2>/dev/null

# Run basic tests
run_test "Help display" "python radio.py --help" 0
run_test "Bad callsign" "python radio.py 'BAD!'" 1
run_test "List audio devices" "python radio.py W1ABC --list-audio" 0

# Add more tests here...

echo "📊 Test Results: $PASSED/$TESTS passed ($FAILED failed)"
```

## **Manual Test Checklist**

For each test session:

1. **Document environment:**
   - Python version: `python --version`
   - OS version: `uname -a` 
   - Hardware: Pi model, USB devices connected

2. **Pick test phase** (start with Phase 1)

3. **Follow test table** systematically

4. **✅ Mark Pass/Fail** and note any issues

5. **For failures:** Note exact error message, command used, environment

## **Test Tips**

- **Test in virtual environment** AND outside it - should fail if not in a virtual environment
- **Test with different USB audio devices**
- **Test network connectivity scenarios** (WiFi, Ethernet, offline)
- **Test GPIO scenarios** (if on actual Pi vs some other Pi)
- **Save test configs** for repeatable testing

## **Success Criteria**

mark with ✅ when complete

- ⬜ All Phase 1-4 tests pass (core functionality)
- ⬜ Error handling is graceful (no Python tracebacks for user errors)
- ⬜ Help text is clear and complete?
- ⬜ Audio device selection works on different hardware
- ⬜ Network configuration applies correctly
- ⬜ Configuration files are created/updated properly

Would you like me to create any specific test scripts or expand on particular test scenarios?
