// Configuration Management Functions

// Configuration management
function loadCurrentConfig() {
	sendWebSocketMessage('get_current_config');
}

function populateEnhancedConfigFromData(config) {
	console.log("📋 DEBUG: populateEnhancedConfigFromData called");
	console.log("📋 DEBUG: config object:", config);
	console.log("📋 DEBUG: metadata:", config._metadata);

	currentConfig = config;
	
	// Update current file display
	if (config._metadata && config._metadata.config_file_path) {
		const currentFileElement = document.getElementById('current-config-file');
		if (currentFileElement) {
			currentFileElement.textContent = config._metadata.config_file_path;
		}
	} else {
		const currentFileElement = document.getElementById('current-config-file');
		if (currentFileElement) {
			currentFileElement.textContent = 'Default configuration';
		}
	}
	
	// Station settings
	if (config.callsign) {
		const callsignElement = document.getElementById('callsign');
		if (callsignElement) {
			callsignElement.value = config.callsign;
			currentStation = config.callsign;
			document.getElementById('current-station').textContent = currentStation;
		}
	}
	
	// Network settings
	if (config.network) {
		if (config.network.target_ip) {
			const targetIpElement = document.getElementById('target-ip');
			if (targetIpElement) targetIpElement.value = config.network.target_ip;
		}
		if (config.network.target_port) {
			const targetPortElement = document.getElementById('target-port');
			if (targetPortElement) targetPortElement.value = config.network.target_port;
		}
		if (config.network.listen_port) {
			const listenPortElement = document.getElementById('listen-port');
			if (listenPortElement) listenPortElement.value = config.network.listen_port;
		}
	}
	
	// Target Device Type settings
	if (config.protocol) {
		if (config.protocol.target_type) {
			const targetTypeElement = document.getElementById('target-type');
			if (targetTypeElement) targetTypeElement.value = config.protocol.target_type;
		}
		if (config.protocol.keepalive_interval) {
			const keepaliveElement = document.getElementById('keepalive-interval');
			if (keepaliveElement) keepaliveElement.value = config.protocol.keepalive_interval;
		}
	}



	// Transcription settings
	if (config.gui && config.gui.transcription) {
		const transcription = config.gui.transcription;
        
		if ('enabled' in transcription) {
			document.getElementById('transcription-enabled').checked = transcription.enabled;
		}
        
		if ('confidence_threshold' in transcription) {
			const threshold = transcription.confidence_threshold;
			document.getElementById('transcription-confidence').value = threshold;
			document.getElementById('confidence-value').textContent = Math.round(threshold * 100) + '%';
		}
        
		if ('language' in transcription) {
			document.getElementById('transcription-language').value = transcription.language;
		}
        
		if ('model_size' in transcription) {
			document.getElementById('model-size').value = transcription.model_size;
		}
	}

	
	// GPIO settings
	if (config.gpio) {
		if (config.gpio.ptt_pin) {
			const pttPinElement = document.getElementById('ptt-pin');
			if (pttPinElement) pttPinElement.value = config.gpio.ptt_pin;
		}
		if (config.gpio.led_pin) {
			const ledPinElement = document.getElementById('led-pin');
			if (ledPinElement) ledPinElement.value = config.gpio.led_pin;
		}
	}
	
	// Debug settings
	if (config.debug) {
		if (config.debug.verbose !== undefined) {
			const verboseElement = document.getElementById('verbose-mode');
			if (verboseElement) verboseElement.checked = config.debug.verbose;
		}
		if (config.debug.quiet !== undefined) {
			const quietElement = document.getElementById('quiet-mode');
			if (quietElement) quietElement.checked = config.debug.quiet;
		}
		if (config.debug.log_level) {
			const logLevelElement = document.getElementById('log-level-config');
			if (logLevelElement) logLevelElement.value = config.debug.log_level;
		}
	}
	
	updateConfigStatus('Configuration loaded successfully');
}


// AI!!! not sure this goes here or some other js file
// Update confidence threshold display
document.getElementById('transcription-confidence').addEventListener('input', function() {
	const value = Math.round(this.value * 100);
	document.getElementById('confidence-value').textContent = value + '%';
});



// Enhanced config data gathering
function gatherEnhancedConfigData() {
	const callsignElement = document.getElementById('callsign');
	const targetIpElement = document.getElementById('target-ip');
	const targetPortElement = document.getElementById('target-port');
	const listenPortElement = document.getElementById('listen-port');
	const targetTypeElement = document.getElementById('target-type');
	const keepaliveElement = document.getElementById('keepalive-interval');
	const pttPinElement = document.getElementById('ptt-pin');
	const ledPinElement = document.getElementById('led-pin');
	const verboseElement = document.getElementById('verbose-mode');
	const quietElement = document.getElementById('quiet-mode');
	const logLevelElement = document.getElementById('log-level-config');

	return {
		callsign: callsignElement ? callsignElement.value.trim() : '',
		network: {
			target_ip: targetIpElement ? targetIpElement.value.trim() : '',
			target_port: targetPortElement ? (parseInt(targetPortElement.value) || 57372) : 57372,
			listen_port: listenPortElement ? (parseInt(listenPortElement.value) || 57372) : 57372
		},
		protocol: {
			target_type: targetTypeElement ? (targetTypeElement.value || 'computer') : 'computer',
			keepalive_interval: keepaliveElement ? (parseFloat(keepaliveElement.value) || 2.0) : 2.0
		},
		gpio: {
			ptt_pin: pttPinElement ? (parseInt(pttPinElement.value) || 23) : 23,
			led_pin: ledPinElement ? (parseInt(ledPinElement.value) || 17) : 17,
			button_bounce_time: 0.02,  // Default
			led_brightness: 1.0        // Default
		},
		debug: {
			verbose: verboseElement ? verboseElement.checked : false,
			quiet: quietElement ? quietElement.checked : false,
			log_level: logLevelElement ? (logLevelElement.value || 'INFO') : 'INFO'
		},
		transcription: {
			enabled: document.getElementById('transcription-enabled').checked,
			confidence_threshold: parseFloat(document.getElementById('transcription-confidence').value),
			language: document.getElementById('transcription-language').value,
			model_size: document.getElementById('model-size').value,
			method: document.getElementById('transcription-enabled').checked ? 'auto' : 'disabled'
		}
	};
}

function applyConfig() {
	const config = gatherEnhancedConfigData();
	if (validateConfig(config)) {
		sendWebSocketMessage('update_config', config);
		showNotification('Applying configuration...', 'info');

		// Update the UI station ID immediately
		if (config.callsign) {
			currentStation = config.callsign;
			const currentStationElement = document.getElementById('current-station');
			if (currentStationElement) {
				currentStationElement.textContent = currentStation;
			}
		}
	}
}

function validateConfig(config) {
	const errors = [];
	
	if (!config.callsign) {
		errors.push('Callsign is required');
	} else if (!/^[A-Z0-9\-\/.]+$/i.test(config.callsign)) {
		errors.push('Callsign contains invalid characters');
	}
	
	if (!config.network.target_ip) {
		errors.push('Target IP is required');
	}
	
	if (config.network.target_port < 1 || config.network.target_port > 65535) {
		errors.push('Target port must be between 1 and 65535');
	}
	
	if (errors.length > 0) {
		showNotification(errors.join('; '), 'error');
		return false;
	}
	
	return true;
}

// Configuration file operations
function createConfigFileEnhanced() {
	const filenameElement = document.getElementById('create-config-filename');
	const filename = filenameElement ? (filenameElement.value.trim() || 'opulent_voice.yaml') : 'opulent_voice.yaml';
	
	const data = {
		filename: filename,
		template_type: 'full'  // Always create full templates with comments
	};

	showOperationProgress('Creating template configuration file...');
	addLogEntry(`Creating template configuration file: ${filename}`, 'info');
	sendWebSocketMessage('create_config', data);
}

function loadConfigFile() {
	const filenameElement = document.getElementById('load-config-filename');
	const filename = filenameElement ? filenameElement.value.trim() : '';
	const data = filename ? { filename } : {};
	
	showOperationProgress('Loading configuration...');
	addLogEntry(`Loading configuration${filename ? ` from ${filename}` : ' (auto-discovery)'}...`, 'info');
	sendWebSocketMessage('load_config', data);
}

function saveConfigFile() {
	const filenameElement = document.getElementById('save-config-filename');
	const filename = filenameElement ? filenameElement.value.trim() : '';
	const data = filename ? { filename } : {};
	
	showOperationProgress('Saving configuration...');
	addLogEntry(`Saving configuration${filename ? ` to ${filename}` : ' (auto-location)'}...`, 'info');
	sendWebSocketMessage('save_config', data);
}

function resetToDefaults() {
	if (confirm('Reset all configuration to defaults? This will clear the current form.')) {
		// Reset form to default values
		const elements = [
			{ id: 'callsign', value: '' },
			{ id: 'target-ip', value: '192.168.2.152' },
			{ id: 'target-port', value: '57372' },
			{ id: 'listen-port', value: '57372' },
			{ id: 'target-type', value: 'computer' },
			{ id: 'keepalive-interval', value: '2.0' },
			{ id: 'ptt-pin', value: '23' },
			{ id: 'led-pin', value: '17' },
			{ id: 'log-level-config', value: 'INFO' }
		];

		elements.forEach(elem => {
			const element = document.getElementById(elem.id);
			if (element) element.value = elem.value;
		});

		const checkboxes = [
			{ id: 'verbose-mode', checked: false },
			{ id: 'quiet-mode', checked: false }
		];

		checkboxes.forEach(cb => {
			const element = document.getElementById(cb.id);
			if (element) element.checked = cb.checked;
		});
		
		updateConfigStatus('Configuration reset to defaults');
		addLogEntry('Configuration form reset to defaults', 'info');
	}
}

function testConnection() {
	addLogEntry('Testing system with current form values...', 'info');
	showOperationProgress('Gathering form data for testing...');
	
	try {
		console.log('📋 DEBUG: Starting form data gathering...');
		
		const formConfig = gatherEnhancedConfigData();
		console.log('📋 DEBUG: Form config gathered:', formConfig);
		console.log('📋 DEBUG: Form config type:', typeof formConfig);
		console.log('📋 DEBUG: Form config keys:', Object.keys(formConfig || {}));
		
		// Check specific fields
		const callsignElement = document.getElementById('callsign');
		const targetIpElement = document.getElementById('target-ip');
		console.log('📋 DEBUG: Callsign field value:', callsignElement ? callsignElement.value : 'not found');
		console.log('📋 DEBUG: Target IP field value:', targetIpElement ? targetIpElement.value : 'not found');
		
		sendWebSocketMessage('test_connection_with_form', {
			form_config: formConfig,
			validate_form: true
		});
		
	} catch (error) {
		console.error('❌ Error in testConnection:', error);
		updateConfigStatus(`❌ Error: ${error.message}`, 'error');
		hideOperationProgress();
	}
}

// Enhanced config message handling
function handleEnhancedConfigMessage(message) {
	console.log('📋 ENHANCED HANDLER DEBUG: Received message type:', message.type);
	console.log('📋 ENHANCED HANDLER DEBUG: Message data:', message.data);
	
	switch (message.type) {
		case 'current_config':
			console.log('📋 ENHANCED HANDLER DEBUG: Processing current_config');
			populateEnhancedConfigFromData(message.data);
			break;
			
		case 'config_loaded':
			console.log('📋 ENHANCED HANDLER DEBUG: Processing config_loaded');
			showNotification(message.data.message, 'success');
			updateConfigStatus(`Loaded: ${message.data.filename}`);
			loadCurrentConfig();
			break;
			
		case 'config_saved':
			console.log('📋 ENHANCED HANDLER DEBUG: Processing config_saved');
			showNotification(message.data.message, 'success');
			updateConfigStatus(`Saved: ${message.data.filename}`);
			break;

		case 'config_created':
			console.log('📋 ENHANCED HANDLER DEBUG: Processing config_created');
			showNotification(message.data.message, 'success');
			updateConfigStatus(`Created: ${message.data.filename}`);
			break;

		case 'config_updated':
			console.log('📋 ENHANCED HANDLER DEBUG: Processing config_updated');
			showNotification(message.data.message, 'success');
			updateConfigStatus('Configuration updated successfully');
			break;

		case 'config_not_found':
			console.log('📋 ENHANCED HANDLER DEBUG: Processing config_not_found');
			showNotification(message.data.message, 'warning');
			updateConfigStatus(`File not found: ${message.data.filename || 'unknown'}`);
			break;

		case 'config_validation_warning':
			console.log('📋 ENHANCED HANDLER DEBUG: Processing config_validation_warning');
			showNotification(message.data.message, 'warning');
			updateConfigStatus(`Warning: ${message.data.message}`);
			break;
			
		case 'connection_test_with_form_result':
			console.log('📋 ENHANCED HANDLER DEBUG: Processing connection_test_with_form_result');
			hideOperationProgress();
			const formTestResult = message.data;
			
			console.log('📋 ENHANCED HANDLER DEBUG: Form validation valid:', formTestResult.form_validation?.valid);
			
			if (formTestResult.form_validation?.valid) {
				// now check for warnings, even if results were valid
				let warningText = '';
				if (formTestResult.form_validation?.field_errors) {
					const fieldErrors = formTestResult.form_validation.field_errors;
        
					Object.keys(fieldErrors).forEach(field => {
						warningText += `${fieldErrors[field]}; `;
					});
				}
        
				// Form is valid, show system test results combined with warnings
				let statusMessage = formTestResult.system_test.success ?
				'System test passed with form values' :
				`System test issues: ${formTestResult.system_test.message}`;

				if (warningText) {	
					statusMessage = `${statusMessage} | ⚠️ ${warningText}`;
				}

				updateConfigStatus(statusMessage, formTestResult.system_test.success ? 'success' : 'warning');
				console.log('📋 ENHANCED HANDLER DEBUG: System test success:', formTestResult.system_test.success);
			} else {
				// Form validation failed
				const errors = formTestResult.form_validation.errors.join(', ');
				updateConfigStatus(`❌ Cannot test - form errors: ${errors}`, 'error');
				console.log('📋 ENHANCED HANDLER DEBUG: Form validation failed:', errors);
			}
			break;

		case 'connection_test_result':
			console.log('📋 ENHANCED HANDLER DEBUG: Processing connection_test_result');
			hideOperationProgress();
			const testResult = message.data;
			if (testResult.success) {
				updateConfigStatus('Connection test passed', 'success');
				showNotification('System test completed successfully', 'success');
			} else {
				updateConfigStatus(`Connection test failed: ${testResult.message}`, 'error');
				showNotification(`Test failed: ${testResult.message}`, 'error');
			}
			break;
			
		default:
			console.log('📋 ENHANCED HANDLER DEBUG: Unknown message type:', message.type);
			// Don't log unknown messages for config-related types
			break;
	}
}

// Progress indication functions
function showOperationProgress(message) {
	const progressEl = document.getElementById('config-operation-progress');
	if (progressEl) {
		const textEl = progressEl.querySelector('.progress-text');
		if (textEl) {
			textEl.textContent = message;
		}
		progressEl.style.display = 'flex';
	}
}

function hideOperationProgress() {
	const progressEl = document.getElementById('config-operation-progress');
	if (progressEl) {
		progressEl.style.display = 'none';
	}
}

// Update config status with better formatting
function updateConfigStatus(message, type = 'info') {
	const statusEl = document.getElementById('config-status');
	if (!statusEl) return;

	const timestamp = new Date().toLocaleTimeString();
	
	statusEl.textContent = `[${timestamp}] ${message}`;
	
	// Add visual feedback based on type
	statusEl.className = `config-status-message status-${type}`;
	
	// Hide progress indicator
	hideOperationProgress();
	
	// Auto-clear after 10 seconds
	setTimeout(() => {
		if (statusEl.textContent.includes(timestamp)) {
			statusEl.textContent = 'Ready to manage configuration files and settings';
			statusEl.className = 'config-status-message';
		}
	}, 10000);
}
