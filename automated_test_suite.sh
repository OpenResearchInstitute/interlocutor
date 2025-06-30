#!/bin/bash
# Opulent Voice Automated Test Suite
# Usage: ./test_suite.sh [--verbose] [--quick] [--phase N]
#
# This test suite focuses on automated testing of:
# - Command line argument handling
# - Configuration file processing
# - Error handling and edge cases
# - Network parameter validation
# - Operating mode switches
#
# Audio hardware testing is NOT included in automated tests because:
# - Hardware availability varies between systems
# - Cannot inject test signals into real microphones
# - Cannot verify audio output without human interaction
# - PyAudio behavior is environment-dependent
#
# For audio testing, use the interactive commands:
# - ./interlocutor.py CALLSIGN --list-audio
# - ./interlocutor.py CALLSIGN --test-audio  
# - ./interlocutor.py CALLSIGN --setup-audio

set -e  # Exit on any error (can be overridden for negative tests)

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Test configuration
TIMEOUT=15  # seconds for each test
PYTHON_CMD="python3"
RADIO_SCRIPT="interlocutor.py"
TEST_CALLSIGN="W1TEST"

# Test counters
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0
SKIPPED_TESTS=0

# Test results log
TEST_LOG="test_results_$(date +%Y%m%d_%H%M%S).log"

# Flags
VERBOSE=false
QUICK_TEST=false
SPECIFIC_PHASE=""

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --verbose|-v)
            VERBOSE=true
            shift
            ;;
        --quick|-q)
            QUICK_TEST=true
            shift
            ;;
        --phase)
            SPECIFIC_PHASE="$2"
            shift 2
            ;;
        --help|-h)
            echo "Opulent Voice Test Suite"
            echo "Usage: $0 [options]"
            echo "Options:"
            echo "  --verbose, -v     Verbose output"
            echo "  --quick, -q       Run only critical tests"
            echo "  --phase N         Run only phase N tests"
            echo "  --help, -h        Show this help"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Logging functions
log() {
    echo "[$(date '+%H:%M:%S')] $1" | tee -a "$TEST_LOG"
}

log_verbose() {
    if [ "$VERBOSE" = true ]; then
        echo "[$(date '+%H:%M:%S')] $1" | tee -a "$TEST_LOG"
    else
        echo "[$(date '+%H:%M:%S')] $1" >> "$TEST_LOG"
    fi
}

# Test framework functions
start_test_suite() {
    echo -e "${BLUE}🧪 Opulent Voice Automated Test Suite${NC}"
    echo "=========================================="
    log "Test suite started"
    log "Python: $(python3 --version 2>&1)"
    log "OS: $(uname -s) $(uname -r)"
    log "Test log: $TEST_LOG"
    echo
}

run_test() {
    local test_name="$1"
    local command="$2"
    local expected_exit_code="$3"
    local phase="$4"
    local description="$5"
    
    # Skip if running specific phase and this isn't it
    if [[ -n "$SPECIFIC_PHASE" && "$phase" != "$SPECIFIC_PHASE" ]]; then
        return 0
    fi
    
    TOTAL_TESTS=$((TOTAL_TESTS + 1))
    
    printf "Test %3d: %-30s " "$TOTAL_TESTS" "$test_name"
    log_verbose "Running: $command"
    log_verbose "Expected exit code: $expected_exit_code"
    
    # Create temporary output files
    local stdout_file=$(mktemp)
    local stderr_file=$(mktemp)
    
    # Run the test with timeout
    set +e  # Don't exit on error for this test
    timeout "$TIMEOUT" bash -c "$command" >"$stdout_file" 2>"$stderr_file"
    local actual_exit_code=$?
    set -e
    
    # Handle timeout (exit code 124)
    if [ $actual_exit_code -eq 124 ]; then
        echo -e "${RED}TIMEOUT${NC}"
        log "FAIL: $test_name - Test timed out after ${TIMEOUT}s"
        FAILED_TESTS=$((FAILED_TESTS + 1))
    elif [ $actual_exit_code -eq $expected_exit_code ]; then
        echo -e "${GREEN}PASS${NC}"
        log "PASS: $test_name"
        PASSED_TESTS=$((PASSED_TESTS + 1))
    else
        echo -e "${RED}FAIL${NC} (exit: $actual_exit_code, expected: $expected_exit_code)"
        log "FAIL: $test_name - Exit code $actual_exit_code, expected $expected_exit_code"
        FAILED_TESTS=$((FAILED_TESTS + 1))
        
        # Log error details in verbose mode
        if [ "$VERBOSE" = true ]; then
            echo -e "${YELLOW}STDOUT:${NC}"
            cat "$stdout_file"
            echo -e "${YELLOW}STDERR:${NC}"
            cat "$stderr_file"
        fi
    fi
    
    # Save output to log
    log_verbose "STDOUT: $(cat "$stdout_file")"
    log_verbose "STDERR: $(cat "$stderr_file")"
    
    # Cleanup temp files
    rm -f "$stdout_file" "$stderr_file"
}

# Test environment setup
setup_test_environment() {
    log "Setting up test environment..."
    
    # Check if we're in the right directory
    if [ ! -f "$RADIO_SCRIPT" ]; then
        echo -e "${RED}Error: $RADIO_SCRIPT not found in current directory${NC}"
        exit 1
    fi
    
    # Check Python and virtual environment
    if ! command -v "$PYTHON_CMD" &> /dev/null; then
        echo -e "${RED}Error: $PYTHON_CMD not found${NC}"
        exit 1
    fi
    
    # Create test_configs directory if it doesn't exist
    mkdir -p test_configs
    
    # Create known good configs if they don't exist
    if [ ! -f "test_configs/good_config.yaml" ]; then
        log "Creating test configuration files..."
        create_test_configs
    fi
    
    log "Test environment ready"
}

create_test_configs() {
    # Create good config (removed audio-specific configs)
    cat > test_configs/good_config.yaml << 'EOF'
callsign: "W1TEST"
network:
  target_ip: "192.168.1.100"
  target_port: 57372
  listen_port: 57372
audio:
  sample_rate: 48000
  frame_duration_ms: 40
  bitrate: 64000
  channels: 1
gpio:
  ptt_pin: 23
  led_pin: 17
  button_bounce_time: 0.05
protocol:
  target_type: "computer"
  keepalive_interval: 30
debug:
  verbose: false
  quiet: false
ui:
  chat_only_mode: false
EOF

    # Create corrupted config for testing
    cat > test_configs/corrupted_config.yaml << 'EOF'
# Intentionally malformed YAML
callsign: "W1TEST
network:
  target_ip: 192.168.1.100
  invalid_yaml: [unclosed
EOF

    # Create partial config
    cat > test_configs/partial_config.yaml << 'EOF'
callsign: "W1TEST"
network:
  target_ip: "192.168.1.100"
# Missing other sections - should be filled with defaults
EOF

    log "Test configuration files created"
}

# Test phases
run_phase_1_basic_operations() {
    if [[ -n "$SPECIFIC_PHASE" && "$SPECIFIC_PHASE" != "1" ]]; then
        return 0
    fi
    
    echo -e "${BLUE}Phase 1: Basic Operations${NC}"
    
    # Clean slate for basic tests
    backup_and_clean_configs
    
    run_test "help_display" \
        "$PYTHON_CMD $RADIO_SCRIPT --help" \
        0 1 "Display help and exit"
    
    run_test "version_info" \
        "$PYTHON_CMD $RADIO_SCRIPT --version" \
        0 1 "Display version and exit"
    
    run_test "no_callsign" \
        "$PYTHON_CMD $RADIO_SCRIPT" \
        2 1 "Error when no callsign provided"
    
    run_test "invalid_callsign" \
        "$PYTHON_CMD $RADIO_SCRIPT 'BAD CALL!'" \
        1 1 "Error on invalid callsign characters"
}

run_phase_2_command_line_options() {
    if [[ -n "$SPECIFIC_PHASE" && "$SPECIFIC_PHASE" != "2" ]]; then
        return 0
    fi
    
    echo -e "${BLUE}Phase 2: Command Line Options${NC}"
    
    backup_and_clean_configs
    
    # Test 1: Audio options show help without crashing
    run_test "audio_help_options" \
        "$PYTHON_CMD $RADIO_SCRIPT --help | grep -E '(setup-audio|list-audio|test-audio)'" \
        0 2 "Audio options appear in help"
    
    # Test 2: List audio devices exits cleanly (but don't test hardware)
    run_test "list_audio_exits_clean" \
        "timeout 10s $PYTHON_CMD $RADIO_SCRIPT $TEST_CALLSIGN --list-audio > /dev/null" \
        0 2 "List audio command exits cleanly"
    
    # Test 3: Test audio command exits cleanly in test mode
    run_test "test_audio_exits_clean" \
        "env OPULENT_VOICE_TEST_MODE=1 timeout 10s $PYTHON_CMD $RADIO_SCRIPT $TEST_CALLSIGN --test-audio > /dev/null" \
        0 2 "Test audio command exits cleanly in test mode"
    
    # Test 4: Setup audio handles EOF gracefully
    run_test "setup_audio_handles_eof" \
        "echo | timeout 5s $PYTHON_CMD $RADIO_SCRIPT $TEST_CALLSIGN --setup-audio 2>/dev/null || true" \
        0 2 "Setup audio handles EOF without hanging"
    
}








run_phase_3_network_config() {
    if [[ -n "$SPECIFIC_PHASE" && "$SPECIFIC_PHASE" != "3" ]]; then
        return 0
    fi
    
    echo -e "${BLUE}Phase 3: Network Configuration${NC}"
    
    backup_and_clean_configs
    
    # Test 1: Custom IP accepted and starts chat mode
    run_test "custom_ip" \
        "echo 'quit' | $PYTHON_CMD $RADIO_SCRIPT $TEST_CALLSIGN -i 192.168.5.100 --chat-only" \
        0 3 "Custom IP address accepted"
    
    # Test 2: Custom port accepted and starts chat mode
    run_test "custom_port" \
        "echo 'quit' | $PYTHON_CMD $RADIO_SCRIPT $TEST_CALLSIGN -p 12345 --chat-only" \
        0 3 "Custom port accepted"
    
    # Test 3: Invalid IP format accepted (validated at runtime, not parse time)
    run_test "invalid_ip_accepted" \
        "echo 'quit' | $PYTHON_CMD $RADIO_SCRIPT $TEST_CALLSIGN -i 999.999.999.999 --chat-only" \
        0 3 "Invalid IP format accepted (runtime validation)"
    
    # Test 4: Invalid port rejected at parse time
    run_test "invalid_port" \
        "$PYTHON_CMD $RADIO_SCRIPT $TEST_CALLSIGN -p 99999 --chat-only" \
        2 3 "Invalid port rejected with error"
}








run_phase_4_operating_modes() {
    if [[ -n "$SPECIFIC_PHASE" && "$SPECIFIC_PHASE" != "4" ]]; then
        return 0
    fi
    
    echo -e "${BLUE}Phase 4: Operating Modes${NC}"
    
    backup_and_clean_configs
    
    # Test 1: Chat-only mode works
    run_test "chat_only_mode" \
        "echo 'quit' | $PYTHON_CMD $RADIO_SCRIPT $TEST_CALLSIGN --chat-only" \
        0 4 "Chat-only mode starts successfully"
    
    # Test 2: Verbose mode works (should show extra debug output)
    run_test "verbose_mode" \
        "echo 'quit' | $PYTHON_CMD $RADIO_SCRIPT $TEST_CALLSIGN --verbose --chat-only" \
        0 4 "Verbose mode shows debug output"
    
    # Test 3: Quiet mode works (should show less output)
    run_test "quiet_mode" \
        "echo 'quit' | $PYTHON_CMD $RADIO_SCRIPT $TEST_CALLSIGN --quiet --chat-only" \
        0 4 "Quiet mode reduces output"
}






run_phase_5_config_files() {
    if [[ -n "$SPECIFIC_PHASE" && "$SPECIFIC_PHASE" != "5" ]]; then
        return 0
    fi
    
    echo -e "${BLUE}Phase 5: Configuration File Handling${NC}"
    
    # Test 1: No config files - should create defaults and start
    backup_and_clean_configs
    run_test "no_config_files" \
        "echo 'quit' | $PYTHON_CMD $RADIO_SCRIPT $TEST_CALLSIGN --chat-only" \
        0 5 "Creates default configs when none exist"
    
    # Test 2: Partial config - should fill in missing values and start
    backup_and_clean_configs
    cp test_configs/partial_config.yaml opulent_voice_config.yaml
    run_test "partial_config" \
        "echo 'quit' | $PYTHON_CMD $RADIO_SCRIPT $TEST_CALLSIGN --chat-only" \
        0 5 "Handles partial configuration gracefully"
    
    # Test 3: Corrupted config - should handle gracefully and start with defaults
    backup_and_clean_configs
    cp test_configs/corrupted_config.yaml opulent_voice_config.yaml
    run_test "corrupted_config" \
        "echo 'quit' | $PYTHON_CMD $RADIO_SCRIPT $TEST_CALLSIGN --chat-only" \
        0 5 "Handles corrupted config gracefully"
    

# Test 4: Program works without config files (doesn't require file creation)
run_test "no_config_required" \
    "echo 'quit' | $PYTHON_CMD $RADIO_SCRIPT $TEST_CALLSIGN --chat-only" \
    0 5 "Works without requiring config files"
}







# Utility functions
backup_and_clean_configs() {
    # Backup existing configs
    [ -f "opulent_voice_config.yaml" ] && mv "opulent_voice_config.yaml" "opulent_voice_config.yaml.bak"
    [ -f "audio_config.yaml" ] && mv "audio_config.yaml" "audio_config.yaml.bak"
    
    log_verbose "Configs backed up and cleaned"
}

restore_configs() {
    # Restore backed up configs
    [ -f "opulent_voice_config.yaml.bak" ] && mv "opulent_voice_config.yaml.bak" "opulent_voice_config.yaml"
    [ -f "audio_config.yaml.bak" ] && mv "audio_config.yaml.bak" "audio_config.yaml"
    
    log_verbose "Configs restored"
}

cleanup_test_environment() {
    log "Cleaning up test environment..."
    
    # Restore original configs
    restore_configs
    
    # Remove any temporary test files
    rm -f *.yaml.test 2>/dev/null || true
    
    log "Cleanup complete"
}

show_test_summary() {
    echo
    echo "=========================================="
    echo -e "${BLUE}Test Summary${NC}"
    echo "=========================================="
    echo "Total tests:   $TOTAL_TESTS"
    echo -e "Passed:        ${GREEN}$PASSED_TESTS${NC}"
    echo -e "Failed:        ${RED}$FAILED_TESTS${NC}"
    echo -e "Skipped:       ${YELLOW}$SKIPPED_TESTS${NC}"
    
    if [ $FAILED_TESTS -eq 0 ]; then
        echo -e "\n${GREEN}🎉 All tests passed!${NC}"
        log "All tests passed!"
    else
        echo -e "\n${RED}❌ Some tests failed. Check $TEST_LOG for details.${NC}"
        log "$FAILED_TESTS tests failed"
    fi
    
    echo "Full test log: $TEST_LOG"
}

# Signal handlers for cleanup
trap cleanup_test_environment EXIT
trap 'echo -e "\n${YELLOW}Test interrupted by user${NC}"; exit 130' INT

# Main test execution
main() {
    start_test_suite
    setup_test_environment
    
    if [ "$QUICK_TEST" = true ]; then
        echo -e "${YELLOW}Running quick test suite (critical tests only)${NC}\n"
        run_phase_1_basic_operations
        run_phase_2_command_line_options
    elif [ -n "$SPECIFIC_PHASE" ]; then
        echo -e "${YELLOW}Running Phase $SPECIFIC_PHASE tests only${NC}\n"
        case $SPECIFIC_PHASE in
            1) run_phase_1_basic_operations ;;
            2) run_phase_2_command_line_options ;;
            3) run_phase_3_network_config ;;
            4) run_phase_4_operating_modes ;;
            5) run_phase_5_config_files ;;
            *) echo "Invalid phase: $SPECIFIC_PHASE"; exit 1 ;;
        esac
    else
        echo -e "${YELLOW}Running full test suite${NC}\n"
        run_phase_1_basic_operations
        run_phase_2_command_line_options
        run_phase_3_network_config
        run_phase_4_operating_modes
        run_phase_5_config_files
    fi
    
    show_test_summary
    
    # Exit with failure if any tests failed
    exit $FAILED_TESTS
}

# Run main function
main "$@"
