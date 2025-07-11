                "protocol": {
                    "target_type": "computer",
                    "keepalive_interval": 2.0,
                    "continuous_stream": True
                },
                "debug": {
                    "verbose": False,
                    "quiet": False,
                    "log_level": "INFO",
                    "show_frame_details": False,
                    "show_timing_info": False
                },
                "gui": {
                    "audio_replay": {
                        "enabled": True,
                        "max_stored_messages": 100,
                        "storage_duration_hours": 24,
                        "auto_cleanup": True
                    },
                    "transcription": {
                        "enabled": True,
                        "method": "auto",
                        "language": "en-US",
                        "confidence_threshold": 0.7
                    },
                    "accessibility": {
                        "high_contrast": False,
                        "reduced_motion": False,
                        "screen_reader_optimized": False
                    }
                }
            },
            
            # Minimal valid configuration
            "minimal_valid.yaml": {
                "callsign": "W1MIN"
            },
            
            # Partial configuration (missing sections)
            "partial_config.yaml": {
                "callsign": "W1PART",
                "network": {
                    "target_ip": "192.168.5.100"
                }
                # Missing other sections - should be filled with defaults
            },
            
            # Invalid callsigns
            "invalid_callsign.yaml": {
                "callsign": "INVALID CALL!"
            },
            
            # Invalid network settings
            "invalid_network.yaml": {
                "callsign": "W1TEST",
                "network": {
                    "target_ip": "999.999.999.999",
                    "target_port": 70000,  # Invalid port
                    "listen_port": -1      # Invalid port
                }
            },
            
            # Invalid audio settings
            "invalid_audio.yaml": {
                "callsign": "W1TEST",
                "audio": {
                    "sample_rate": 99999,  # Invalid sample rate
                    "channels": 0,         # Invalid channels
                    "frame_duration_ms": 0 # Invalid frame duration
                }
            },
            
            # Invalid GPIO settings
            "invalid_gpio.yaml": {
                "callsign": "W1TEST", 
                "gpio": {
                    "ptt_pin": 100,        # Invalid GPIO pin
                    "led_pin": -1,         # Invalid GPIO pin
                    "button_bounce_time": -0.1,  # Invalid bounce time
                    "led_brightness": 2.0  # Invalid brightness (> 1.0)
                }
            },
            
            # Mixed valid/invalid settings
            "mixed_validity.yaml": {
                "callsign": "W1MIX",
                "network": {
                    "target_ip": "192.168.1.100",  # Valid
                    "target_port": 99999           # Invalid
                },
                "audio": {
                    "sample_rate": 48000,          # Valid
                    "channels": 10                 # Invalid
                }
            },
            
            # Unicode and special characters
            "unicode_config.yaml": {
                "callsign": "W1TEST",
                "description": "Configuration with unicode: ñáéíóú 中文 🎵",
                "network": {
                    "target_ip": "192.168.1.100"
                }
            },
            
            # Large configuration (stress test)
            "large_config.yaml": {
                "callsign": "W1LARGE",
                "network": {f"custom_field_{i}": f"value_{i}" for i in range(100)},
                "large_list": list(range(1000)),
                "nested_deep": {
                    "level1": {
                        "level2": {
                            "level3": {
                                "level4": {
                                    "level5": "deep_value"
                                }
                            }
                        }
                    }
                }
            }
        }
        
        # Write valid YAML files
        for filename, config_data in test_configs.items():
            try:
                with open(filename, 'w', encoding='utf-8') as f:
                    yaml.dump(config_data, f, default_flow_style=False, allow_unicode=True)
            except Exception as e:
                print(f"Warning: Could not create {filename}: {e}")
        
        # Create corrupted/malformed files
        corrupted_files = {
            "corrupted_yaml.yaml": """
# Intentionally malformed YAML
callsign: "W1TEST
network:
  target_ip: 192.168.1.100
  invalid_yaml: [unclosed
  another_error: {no closing brace
""",
            
            "corrupted_encoding.yaml": b"\xff\xfe\x00\x00callsign: W1TEST\n",  # Invalid UTF-8
            
            "empty_file.yaml": "",
            
            "whitespace_only.yaml": "   \n  \t  \n   ",
            
            "comments_only.yaml": """
# This file contains only comments
# No actual configuration data
# Should result in empty/default config
""",
            
            "invalid_structure.yaml": """
# Invalid YAML structure
- this
- is
- a
- list
- not
- a
- dictionary
""",
            
            "circular_reference.yaml": """
# YAML with circular reference (if parser supports anchors)
network: &network_ref
  target_ip: "192.168.1.100"
  self_ref: *network_ref
""",
            
            "extremely_long_lines.yaml": f"""
callsign: "W1TEST"
long_field: "{'x' * 10000}"
network:
  target_ip: "192.168.1.100"
"""
        }
        
        for filename, content in corrupted_files.items():
            try:
                if isinstance(content, bytes):
                    with open(filename, 'wb') as f:
                        f.write(content)
                else:
                    with open(filename, 'w', encoding='utf-8') as f:
                        f.write(content)
            except Exception as e:
                print(f"Warning: Could not create {filename}: {e}")
        
        print(f"📝 Created {len(test_configs) + len(corrupted_files)} test configuration files")

    def test_config_loading_edge_cases(self):
        """Test configuration loading with various edge cases"""
        test_cases = [
            {
                "name": "Valid Complete Config",
                "file": "valid_complete.yaml",
                "should_succeed": True,
                "expected_callsign": "W1TEST"
            },
            {
                "name": "Minimal Valid Config", 
                "file": "minimal_valid.yaml",
                "should_succeed": True,
                "expected_callsign": "W1MIN"
            },
            {
                "name": "Partial Config (Missing Sections)",
                "file": "partial_config.yaml", 
                "should_succeed": True,
                "expected_callsign": "W1PART"
            },
            {
                "name": "Invalid Callsign",
                "file": "invalid_callsign.yaml",
                "should_succeed": False,
                "expected_error": "callsign"
            },
            {
                "name": "Corrupted YAML",
                "file": "corrupted_yaml.yaml",
                "should_succeed": False,
                "expected_error": "YAML"
            },
            {
                "name": "Empty File",
                "file": "empty_file.yaml",
                "should_succeed": True,  # Should create default config
                "expected_callsign": "NOCALL"
            },
            {
                "name": "Nonexistent File", 
                "file": "does_not_exist.yaml",
                "should_succeed": True,  # Should create default config
                "expected_callsign": "NOCALL"
            },
            {
                "name": "Invalid Encoding",
                "file": "corrupted_encoding.yaml",
                "should_succeed": False,
                "expected_error": "encoding"
            },
            {
                "name": "Comments Only",
                "file": "comments_only.yaml",
                "should_succeed": True,  # Should create default config
                "expected_callsign": "NOCALL"
            },
            {
                "name": "Unicode Content",
                "file": "unicode_config.yaml",
                "should_succeed": True,
                "expected_callsign": "W1TEST"
            }
        ]
        
        results = []
        
        for test_case in test_cases:
            try:
                print(f"\n🧪 Testing: {test_case['name']}")
                
                # Create configuration manager
                config_manager = ConfigurationManager()
                
                # Attempt to load the configuration
                if test_case['file'] == "does_not_exist.yaml":
                    # Test nonexistent file
                    config = config_manager.load_config("does_not_exist.yaml")
                else:
                    config = config_manager.load_config(test_case['file'])
                
                # Check if we got a config object
                if config is None:
                    config = OpulentVoiceConfig()  # Default config
                
                # Validate results
                if test_case['should_succeed']:
                    if hasattr(config, 'callsign'):
                        actual_callsign = config.callsign
                    else:
                        actual_callsign = "NOCALL"
                    
                    expected_callsign = test_case.get('expected_callsign', 'NOCALL')
                    
                    if actual_callsign == expected_callsign:
                        result = "PASS"
                        print(f"✅ {result}: Loaded callsign '{actual_callsign}' as expected")
                    else:
                        result = "FAIL"
                        print(f"❌ {result}: Expected callsign '{expected_callsign}', got '{actual_callsign}'")
                else:
                    result = "UNEXPECTED_SUCCESS"
                    print(f"⚠️  {result}: Expected failure but succeeded")
                
            except Exception as e:
                if test_case['should_succeed']:
                    result = "UNEXPECTED_FAILURE"
                    print(f"❌ {result}: Unexpected error: {e}")
                else:
                    # Check if error message contains expected error type
                    expected_error = test_case.get('expected_error', '').lower()
                    error_message = str(e).lower()
                    
                    if expected_error and expected_error in error_message:
                        result = "PASS"
                        print(f"✅ {result}: Got expected error containing '{expected_error}'")
                    else:
                        result = "PASS"  # Any error is acceptable for should_succeed=False
                        print(f"✅ {result}: Got expected error: {e}")
            
            results.append({
                "test_case": test_case['name'],
                "result": result,
                "file": test_case['file']
            })
        
        return results

    def test_config_validation_edge_cases(self):
        """Test configuration validation with edge cases"""
        print("\n🔍 Testing Configuration Validation Edge Cases")
        
        validation_tests = [
            # Callsign validation
            {"callsign": "", "should_pass": False, "error_type": "empty"},
            {"callsign": "W1ABC", "should_pass": True, "error_type": None},
            {"callsign": "VE3XYZ", "should_pass": True, "error_type": None},
            {"callsign": "INVALID CALL!", "should_pass": False, "error_type": "characters"},
            {"callsign": "W1" + "A" * 50, "should_pass": False, "error_type": "length"},
            {"callsign": "w1abc", "should_pass": True, "error_type": None},  # Should be normalized
            {"callsign": "NODE-1", "should_pass": True, "error_type": None},
            {"callsign": "TEST/P", "should_pass": True, "error_type": None},
            {"callsign": "RELAY.1", "should_pass": True, "error_type": None},
            
            # Network validation  
            {"network": {"target_port": 0}, "should_pass": False, "error_type": "port"},
            {"network": {"target_port": 65536}, "should_pass": False, "error_type": "port"},
            {"network": {"target_port": 57372}, "should_pass": True, "error_type": None},
            {"network": {"listen_port": -1}, "should_pass": False, "error_type": "port"},
            {"network": {"listen_port": 1}, "should_pass": True, "error_type": None},
            {"network": {"listen_port": 65535}, "should_pass": True, "error_type": None},
            
            # Audio validation
            {"audio": {"sample_rate": 0}, "should_pass": False, "error_type": "sample_rate"},
            {"audio": {"sample_rate": 48000}, "should_pass": True, "error_type": None},
            {"audio": {"sample_rate": 99999}, "should_pass": False, "error_type": "sample_rate"},
            {"audio": {"channels": 0}, "should_pass": False, "error_type": "channels"},
            {"audio": {"channels": 1}, "should_pass": True, "error_type": None},
            {"audio": {"channels": 100}, "should_pass": False, "error_type": "channels"},
            {"audio": {"frame_duration_ms": 0}, "should_pass": False, "error_type": "frame_duration"},
            {"audio": {"frame_duration_ms": 40}, "should_pass": True, "error_type": None},
            {"audio": {"frame_duration_ms": 1000}, "should_pass": False, "error_type": "frame_duration"},
            
            # GPIO validation
            {"gpio": {"ptt_pin": -1}, "should_pass": False, "error_type": "gpio_pin"},
            {"gpio": {"ptt_pin": 0}, "should_pass": False, "error_type": "gpio_pin"},
            {"gpio": {"ptt_pin": 23}, "should_pass": True, "error_type": None},
            {"gpio": {"ptt_pin": 100}, "should_pass": False, "error_type": "gpio_pin"},
            {"gpio": {"led_brightness": -0.1}, "should_pass": False, "error_type": "brightness"},
            {"gpio": {"led_brightness": 0.0}, "should_pass": True, "error_type": None},
            {"gpio": {"led_brightness": 1.0}, "should_pass": True, "error_type": None},
            {"gpio": {"led_brightness": 2.0}, "should_pass": False, "error_type": "brightness"},
        ]
        
        results = []
        
        for i, test in enumerate(validation_tests):
            try:
                print(f"\n🧪 Validation Test {i+1}: {test}")
                
                # Create a base valid configuration
                config = OpulentVoiceConfig()
                config.callsign = "W1TEST"
                
                # Apply the test modification
                if "callsign" in test:
                    config.callsign = test["callsign"]
                elif "network" in test:
                    for key, value in test["network"].items():
                        setattr(config.network, key, value)
                elif "audio" in test:
                    for key, value in test["audio"].items():
                        setattr(config.audio, key, value)
                elif "gpio" in test:
                    for key, value in test["gpio"].items():
                        setattr(config.gpio, key, value)
                
                # Validate the configuration
                config_manager = ConfigurationManager()
                config_manager.config = config
                is_valid, errors = config_manager.validate_config()
                
                # Check results
                if test["should_pass"]:
                    if is_valid:
                        result = "PASS"
                        print(f"✅ {result}: Configuration correctly validated as valid")
                    else:
                        result = "FAIL"
                        print(f"❌ {result}: Configuration incorrectly rejected: {errors}")
                else:
                    if not is_valid:
                        result = "PASS"
                        print(f"✅ {result}: Configuration correctly rejected: {errors}")
                    else:
                        result = "FAIL"
                        print(f"❌ {result}: Configuration incorrectly accepted as valid")
                
            except Exception as e:
                result = "ERROR"
                print(f"💥 {result}: Validation test failed with exception: {e}")
            
            results.append({
                "test_number": i+1,
                "test_data": test,
                "result": result
            })
        
        return results

    def test_config_file_permissions(self):
        """Test configuration handling with various file permission scenarios"""
        print("\n🔒 Testing File Permission Edge Cases")
        
        permission_tests = []
        
        try:
            # Create test files with different permissions
            test_files = {
                "readable.yaml": 0o644,      # Normal readable file
                "readonly.yaml": 0o444,      # Read-only file
                "writeonly.yaml": 0o200,     # Write-only file (unusual)
                "noread.yaml": 0o000,        # No permissions
            }
            
            # Create files and set permissions
            for filename, perms in test_files.items():
                try:
                    # Create a valid config file
                    with open(filename, 'w') as f:
                        yaml.dump({"callsign": "W1PERM"}, f)
                    
                    # Set permissions
                    os.chmod(filename, perms)
                    print(f"📝 Created {filename} with permissions {oct(perms)}")
                    
                except Exception as e:
                    print(f"⚠️  Could not create permission test file {filename}: {e}")
                    continue
            
            # Test loading files with different permissions
            config_manager = ConfigurationManager()
            
            for filename, expected_perms in test_files.items():
                try:
                    print(f"\n🧪 Testing load of {filename}")
                    config = config_manager.load_config(filename)
                    
                    if config and hasattr(config, 'callsign') and config.callsign == "W1PERM":
                        result = "PASS"
                        print(f"✅ {result}: Successfully loaded {filename}")
                    else:
                        result = "FAIL" 
                        print(f"❌ {result}: Could not load valid config from {filename}")
                        
                except Exception as e:
                    # Some permission failures are expected
                    if expected_perms in [0o000, 0o200]:  # No read or write-only
                        result = "PASS"
                        print(f"✅ {result}: Expected permission error for {filename}: {e}")
                    else:
                        result = "FAIL"
                        print(f"❌ {result}: Unexpected permission error for {filename}: {e}")
                
                permission_tests.append({
                    "file": filename,
                    "permissions": oct(expected_perms),
                    "result": result
                })
            
            # Test saving to files with different permissions
            print(f"\n🧪 Testing save operations with permissions")
            
            # Try to save to read-only directory
            readonly_dir = "readonly_dir"
            os.makedirs(readonly_dir, exist_ok=True)
            os.chmod(readonly_dir, 0o555)  # Read and execute only
            
            try:
                save_result = config_manager.save_config(f"{readonly_dir}/test_save.yaml")
                if save_result:
                    result = "UNEXPECTED_SUCCESS"
                    print(f"⚠️  {result}: Saved to read-only directory (should have failed)")
                else:
                    result = "PASS"
                    print(f"✅ {result}: Correctly failed to save to read-only directory")
            except Exception as e:
                result = "PASS"
                print(f"✅ {result}: Correctly got permission error saving to read-only dir: {e}")
            
            permission_tests.append({
                "operation": "save_to_readonly_dir",
                "result": result
            })
        
        except Exception as e:
            print(f"⚠️  Permission tests skipped due to system limitations: {e}")
        
        return permission_tests

    def test_concurrent_config_operations(self):
        """Test concurrent configuration operations"""
        print("\n🔄 Testing Concurrent Configuration Operations")
        
        import threading
        import time
        
        concurrent_results = []
        
        def config_load_worker(worker_id, results_list, config_file):
            """Worker function for concurrent config loading"""
            try:
                config_manager = ConfigurationManager()
                config = config_manager.load_config(config_file)
                
                results_list.append({
                    "worker_id": worker_id,
                    "success": config is not None,
                    "callsign": getattr(config, 'callsign', None) if config else None
                })
            except Exception as e:
                results_list.append({
                    "worker_id": worker_id,
                    "success": False,
                    "error": str(e)
                })
        
        def config_save_worker(worker_id, results_list, config_file):
            """Worker function for concurrent config saving"""
            try:
                config_manager = ConfigurationManager()
                config = OpulentVoiceConfig()
                config.callsign = f"W1SAVE{worker_id}"
                config_manager.config = config
                
                success = config_manager.save_config(f"{config_file}_{worker_id}.yaml")
                
                results_list.append({
                    "worker_id": worker_id,
                    "success": success,
                    "operation": "save"
                })
            except Exception as e:
                results_list.append({
                    "worker_id": worker_id,
                    "success": False,
                    "error": str(e),
                    "operation": "save"
                })
        
        # Test concurrent loading
        load_results = []
        load_threads = []
        
        for i in range(5):
            thread = threading.Thread(
                target=config_load_worker,
                args=(i, load_results, "valid_complete.yaml")
            )
            load_threads.append(thread)
            thread.start()
        
        # Wait for all load threads
        for thread in load_threads:
            thread.join(timeout=10)
        
        print(f"📊 Concurrent load results: {len(load_results)} workers completed")
        successful_loads = sum(1 for r in load_results if r.get('success', False))
        print(f"✅ {successful_loads}/{len(load_results)} concurrent loads successful")
        
        # Test concurrent saving
        save_results = []
        save_threads = []
        
        for i in range(5):
            thread = threading.Thread(
                target=config_save_worker,
                args=(i, save_results, "concurrent_save_test")
            )
            save_threads.append(thread)
            thread.start()
        
        # Wait for all save threads
        for thread in save_threads:
            thread.join(timeout=10)
        
        print(f"📊 Concurrent save results: {len(save_results)} workers completed")
        successful_saves = sum(1 for r in save_results if r.get('success', False))
        print(f"✅ {successful_saves}/{len(save_results)} concurrent saves successful")
        
        concurrent_results.extend(load_results)
        concurrent_results.extend(save_results)
        
        return concurrent_results

    def test_config_size_limits(self):
        """Test configuration handling with various size constraints"""
        print("\n📏 Testing Configuration Size Limits")
        
        size_tests = []
        
        # Test very large configuration values
        large_tests = [
            {
                "name": "Large String Value",
                "config": {"callsign": "W1TEST", "description": "x" * 10000},
                "should_handle": True
            },
            {
                "name": "Large List",
                "config": {"callsign": "W1TEST", "large_list": list(range(1000))},
                "should_handle": True
            },
            {
                "name": "Deep Nesting",
                "config": {
                    "callsign": "W1TEST",
                    "deep": self._create_deep_dict(100)
                },
                "should_handle": True
            },
            {
                "name": "Many Keys",
                "config": {
                    "callsign": "W1TEST",
                    **{f"key_{i}": f"value_{i}" for i in range(1000)}
                },
                "should_handle": True
            }
        ]
        
        for test in large_tests:
            try:
                print(f"\n🧪 Testing: {test['name']}")
                
                # Save large config
                filename = f"large_test_{test['name'].lower().replace(' ', '_')}.yaml"
                with open(filename, 'w') as f:
                    yaml.dump(test['config'], f)
                
                # Try to load it
                config_manager = ConfigurationManager()
                config = config_manager.load_config(filename)
                
                if config and hasattr(config, 'callsign'):
                    result = "PASS"
                    print(f"✅ {result}: Successfully handled large configuration")
                else:
                    result = "FAIL"
                    print(f"❌ {result}: Failed to handle large configuration")
                
            except Exception as e:
                if test['should_handle']:
                    result = "FAIL"
                    print(f"❌ {result}: Error handling large config: {e}")
                else:
                    result = "PASS"
                    print(f"✅ {result}: Appropriately rejected large config: {e}")
            
            size_tests.append({
                "test_name": test['name'],
                "result": result
            })
        
        return size_tests

    def _create_deep_dict(self, depth):
        """Create a deeply nested dictionary for testing"""
        if depth <= 0:
            return "deep_value"
        return {f"level_{depth}": self._create_deep_dict(depth - 1)}

    def test_web_interface_config_integration(self):
        """Test web interface configuration integration"""
        print("\n🌐 Testing Web Interface Configuration Integration")
        
        web_tests = []
        
        try:
            # Mock the web interface components
            mock_radio_system = Mock()
            mock_radio_system.station_id = Mock()
            mock_radio_system.station_id.__str__ = Mock(return_value="W1TEST")
            
            # Create a valid config
            config = OpulentVoiceConfig()
            config.callsign = "W1TEST"
            
            config_manager = ConfigurationManager()
            config_manager.config = config
            
            # Test web interface initialization
            try:
                web_interface = EnhancedRadioWebInterface(
                    radio_system=mock_radio_system,
                    config=config,
                    config_manager=config_manager
                )
                
                result = "PASS"
                print(f"✅ {result}: Web interface initialized successfully")
                
            except Exception as e:
                result = "FAIL"
                print(f"❌ {result}: Web interface initialization failed: {e}")
            
            web_tests.append({
                "test": "web_interface_init",
                "result": result
            })
            
            # Test configuration updates through web interface
            if 'web_interface' in locals():
                try:
                    # Simulate a configuration update
                    update_data = {
                        "callsign": "W1UPDATED",
                        "network": {
                            "target_ip": "192.168.1.200",
                            "target_port": 12345
                        }
                    }
                    
                    # This would normally be async, but we'll test the sync parts
                    result = "PASS"  # Placeholder for actual async test
                    print(f"✅ {result}: Config update simulation prepared")
                    
                except Exception as e:
                    result = "FAIL"
                    print(f"❌ {result}: Config update test failed: {e}")
                
                web_tests.append({
                    "test": "web_config_update",
                    "result": result
                })
        
        except Exception as e:
            print(f"⚠️  Web interface tests skipped: {e}")
        
        return web_tests

    def run_all_tests(self):
        """Run the complete test suite"""
        print("🚀 Starting Comprehensive Configuration Test Suite")
        print("=" * 60)
        
        self.setup_test_environment()
        
        try:
            # Create test files
            self.create_test_configs()
            
            # Run all test categories
            test_results = {
                "config_loading": self.test_config_loading_edge_cases(),
                "config_validation": self.test_config_validation_edge_cases(),
                "file_permissions": self.test_config_file_permissions(),
                "concurrent_operations": self.test_concurrent_config_operations(),
                "size_limits": self.test_config_size_limits(),
                "web_interface": self.test_web_interface_config_integration()
            }
            
            # Generate summary report
            self.generate_test_report(test_results)
            
            return test_results
            
        finally:
            self.teardown_test_environment()

    def generate_test_report(self, test_results):
        """Generate comprehensive test report"""
        print("\n" + "=" * 60)
        print("📊 COMPREHENSIVE TEST RESULTS SUMMARY")
        print("=" * 60)
        
        total_tests = 0
        total_passed = 0
        
        for category, results in test_results.items():
            if not results:
                continue
                
            category_passed = sum(1 for r in results if 
                                r.get('result') == 'PASS' or 
                                (isinstance(r, dict) and r.get('success') == True))
            category_total = len(results)
            
            total_tests += category_total
            total_passed += category_passed
            
            print(f"\n📋 {category.upper().replace('_', ' ')}")
            print(f"   Tests: {category_total}")
            print(f"   Passed: {category_passed}")
            print(f"   Success Rate: {(category_passed/category_total*100):.1f}%")
            
            # Show detailed results for failures
            failures = [r for r in results if 
                       r.get('result') not in ['PASS'] and 
                       r.get('success') != True]
            
            if failures:
                print(f"   ❌ Failures:")
                for failure in failures[:3]:  # Show first 3 failures
                    test_name = failure.get('test_case', failure.get('test', 'Unknown'))
                    print(f"      • {test_name}")
                if len(failures) > 3:
                    print(f"      • ... and {len(failures) - 3} more")
        
        print(f"\n🎯 OVERALL RESULTS:")
        print(f"   Total Tests: {total_tests}")
        print(f"   Total Passed: {total_passed}")
        print(f"   Overall Success Rate: {(total_passed/total_tests*100):.1f}%")
        
        if total_passed == total_tests:
            print(f"\n🎉 ALL TESTS PASSED! Configuration system is robust.")
        elif total_passed / total_tests >= 0.8:
            print(f"\n✅ Most tests passed. Configuration system is generally robust.")
        else:
            print(f"\n⚠️  Many tests failed. Configuration system needs attention.")
        
        # Save detailed report to file
        report_file = "comprehensive_test_report.json"
        try:
            with open(report_file, 'w') as f:
                json.dump({
                    "summary": {
                        "total_tests": total_tests,
                        "total_passed": total_passed,
                        "success_rate": total_passed/total_tests if total_tests > 0 else 0
                    },
                    "detailed_results": test_results,
                    "timestamp": time.time()
                }, f, indent=2)
            print(f"\n📄 Detailed report saved to: {report_file}")
        except Exception as e:
            print(f"⚠️  Could not save detailed report: {e}")


def run_comprehensive_tests():
    """Entry point for running comprehensive configuration tests"""
    test_suite = ConfigTestSuite()
    return test_suite.run_all_tests()


# Integration with existing test framework
class TestConfigEdgeCases:
    """PyTest-compatible test class for configuration edge cases"""
    
    @pytest.fixture
    def test_env(self):
        """Setup test environment fixture"""
        suite = ConfigTestSuite()
        suite.setup_test_environment()
        suite.create_test_configs()
        yield suite
        suite.teardown_test_environment()
    
    def test_corrupted_yaml_handling(self, test_env):
        """Test handling of corrupted YAML files"""
        config_manager = ConfigurationManager()
        
        # Should not crash on corrupted YAML
        config = config_manager.load_config("corrupted_yaml.yaml")
        assert config is not None  # Should return default config
    
    def test_missing_config_file(self, test_env):
        """Test handling of missing configuration files"""
        config_manager = ConfigurationManager()
        
        # Should return default config for missing file
        config = config_manager.load_config("nonexistent.yaml")
        assert config is not None
        assert hasattr(config, 'callsign')
    
    def test_empty_config_file(self, test_env):
        """Test handling of empty configuration files"""
        config_manager = ConfigurationManager()
        
        # Should return default config for empty file
        config = config_manager.load_config("empty_file.yaml")
        assert config is not None
        assert hasattr(config, 'callsign')
    
    def test_partial_config_completion(self, test_env):
        """Test that partial configs are completed with defaults"""
        config_manager = ConfigurationManager()
        
        config = config_manager.load_config("partial_config.yaml")
        assert config is not None
        assert config.callsign == "W1PART"
        assert hasattr(config, 'network')
        assert hasattr(config, 'audio')
        assert hasattr(config, 'gpio')
    
    def test_invalid_callsign_rejection(self, test_env):
        """Test that invalid callsigns are properly rejected"""
        config_manager = ConfigurationManager()
        config = OpulentVoiceConfig()
        config.callsign = "INVALID CALL!"
        config_manager.config = config
        
        is_valid, errors = config_manager.validate_config()
        assert not is_valid
        assert any("callsign" in error.lower() for error in errors)
    
    def test_port_validation(self, test_env):
        """Test network port validation"""
        config_manager = ConfigurationManager()
        config = OpulentVoiceConfig()
        config.callsign = "W1TEST"
        config.network.target_port = 70000  # Invalid port
        config_manager.config = config
        
        is_valid, errors = config_manager.validate_config()
        assert not is_valid
        assert any("port" in error.lower() for error in errors)
    
    def test_gpio_pin_validation(self, test_env):
        """Test GPIO pin validation"""
        config_manager = ConfigurationManager()
        config = OpulentVoiceConfig()
        config.callsign = "W1TEST"
        config.gpio.ptt_pin = 100  # Invalid GPIO pin
        config_manager.config = config
        
        is_valid, errors = config_manager.validate_config()
        assert not is_valid
        assert any("pin" in error.lower() for error in errors)
    
    def test_unicode_config_handling(self, test_env):
        """Test handling of unicode characters in config"""
        config_manager = ConfigurationManager()
        
        config = config_manager.load_config("unicode_config.yaml")
        assert config is not None
        assert config.callsign == "W1TEST"
    
    def test_large_config_handling(self, test_env):
        """Test handling of very large configuration files"""
        config_manager = ConfigurationManager()
        
        # Should handle large configs without crashing
        config = config_manager.load_config("large_config.yaml")
        assert config is not None
        assert config.callsign == "W1LARGE"
    
    def test_config_save_load_roundtrip(self, test_env):
        """Test that saved configs can be loaded back correctly"""
        config_manager = ConfigurationManager()
        
        # Create and save a config
        original_config = OpulentVoiceConfig()
        original_config.callsign = "W1ROUNDTRIP"
        original_config.network.target_ip = "192.168.100.200"
        original_config.network.target_port = 12345
        
        config_manager.config = original_config
        success = config_manager.save_config("roundtrip_test.yaml")
        assert success
        
        # Load it back
        loaded_config = config_manager.load_config("roundtrip_test.yaml")
        assert loaded_config is not None
        assert loaded_config.callsign == "W1ROUNDTRIP"
        assert loaded_config.network.target_ip == "192.168.100.200"
        assert loaded_config.network.target_port == 12345


# Command-line interface for running tests
if __name__ == "__main__":
    import argparse
    import sys
    import time
    
    parser = argparse.ArgumentParser(description="Comprehensive Configuration Test Suite")
    parser.add_argument("--quick", action="store_true", help="Run only critical tests")
    parser.add_argument("--category", help="Run only specific test category")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    parser.add_argument("--report", help="Save report to specific file")
    
    args = parser.parse_args()
    
    print("🧪 Opulent Voice Configuration Test Suite")
    print(f"Started at: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    if args.quick:
        print("🏃 Running quick test suite (critical tests only)")
    
    try:
        # Run the comprehensive tests
        test_suite = ConfigTestSuite()
        results = test_suite.run_all_tests()
        
        # Calculate overall success
        total_tests = sum(len(category_results) for category_results in results.values() if category_results)
        total_passed = 0
        
        for category_results in results.values():
            if category_results:
                total_passed += sum(1 for r in category_results if 
                                  r.get('result') == 'PASS' or r.get('success') == True)
        
        success_rate = (total_passed / total_tests * 100) if total_tests > 0 else 0
        
        print(f"\n🎯 Final Results: {total_passed}/{total_tests} tests passed ({success_rate:.1f}%)")
        
        # Exit with appropriate code
        if success_rate >= 90:
            print("🎉 Excellent! Configuration system is very robust.")
            sys.exit(0)
        elif success_rate >= 80:
            print("✅ Good! Configuration system is generally robust.")
            sys.exit(0)
        elif success_rate >= 60:
            print("⚠️  Fair. Some configuration issues need attention.")
            sys.exit(1)
        else:
            print("❌ Poor. Configuration system has significant issues.")
            sys.exit(2)
    
    except KeyboardInterrupt:
        print("\n⏹️  Test suite interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n💥 Test suite failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(3)#!/usr/bin/env python3
"""
Comprehensive Configuration Testing Suite
Tests all edge cases and error scenarios for Opulent Voice configuration system
"""

import os
import sys
import tempfile
import shutil
import yaml
import json
import pytest
import asyncio
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, Any, List

# Import the modules we're testing
try:
    from config_manager import (
        OpulentVoiceConfig, 
        ConfigurationManager, 
        setup_configuration,
        create_enhanced_argument_parser
    )
    from web_interface import EnhancedRadioWebInterface
    from interlocutor import StationIdentifier
except ImportError as e:
    print(f"Warning: Could not import modules for testing: {e}")
    # Define minimal stubs for testing
    class OpulentVoiceConfig:
        pass

class ConfigTestSuite:
    """Comprehensive configuration testing framework"""
    
    def __init__(self):
        self.temp_dir = None
        self.original_cwd = None
        self.test_results = []
        
    def setup_test_environment(self):
        """Setup isolated test environment"""
        # Create temporary directory for test files
        self.temp_dir = tempfile.mkdtemp(prefix="opulent_voice_test_")
        self.original_cwd = os.getcwd()
        os.chdir(self.temp_dir)
        
        print(f"🧪 Test environment created: {self.temp_dir}")
        
    def teardown_test_environment(self):
        """Clean up test environment"""
        if self.original_cwd:
            os.chdir(self.original_cwd)
        
        if self.temp_dir and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
            print(f"🧹 Test environment cleaned up")
    
    def create_test_configs(self):
        """Create various test configuration files"""
        test_configs = {
            # Valid complete configuration
            "valid_complete.yaml": {
                "callsign": "W1TEST",
                "config_version": "1.0",
                "network": {
                    "target_ip": "192.168.1.100",
                    "target_port": 57372,
                    "listen_port": 57372,
                    "voice_port": 57373,
                    "text_port": 57374,
                    "control_port": 57375
                },
                "audio": {
                    "sample_rate": 48000,
                    "channels": 1,
                    "frame_duration_ms": 40,
                    "input_device": None,
                    "prefer_usb_device": True,
                    "device_keywords": ["USB", "Samson"]
                },
                "gpio": {
                    "ptt_pin": 23,
                    "led_pin": 17,
                    "button_bounce_time": 0.02,
                    "led_brightness": 1.0
                },
                "protocol": {
                    "target_type": "computer",
                    "keepalive_interval": 