// Main Application Logic for Opulent Voice Radio Interface

// Global application state
let ws = null;
let currentStation = 'CONNECTING...';
let messageCount = { sent: 0, received: 0 };
let startTime = Date.now();
let pttActive = false;
let currentConfig = {};
let reconnectAttempts = 0;
let maxReconnectAttempts = 10;
let reconnectDelay = 1000;

// Initialize welcome time
document.addEventListener('DOMContentLoaded', function() {
	const welcomeTimeElement = document.getElementById('welcome-time');
	if (welcomeTimeElement) {
		welcomeTimeElement.textContent = new Date().toLocaleTimeString();
	}
});

// Tab switching functionality
function switchTab(tabName) {
	document.querySelectorAll('.tab-button').forEach(btn => {
		btn.classList.remove('active');
		btn.setAttribute('aria-selected', 'false');
	});
	
	if (tabName === 'chat') {
		document.getElementById('chat-tab').classList.add('active');
		document.getElementById('chat-tab').setAttribute('aria-selected', 'true');
		document.getElementById('chat-panel').style.display = 'block';
		document.getElementById('config-panel').style.display = 'none';
	} else if (tabName === 'config') {
		document.getElementById('config-tab').classList.add('active');
		document.getElementById('config-tab').setAttribute('aria-selected', 'true');
		document.getElementById('chat-panel').style.display = 'none';
		document.getElementById('config-panel').style.display = 'block';
		
		if (ws && ws.readyState === WebSocket.OPEN) {
			console.log("📋 DEBUG: Requesting current config");
			sendWebSocketMessage('get_current_config');
		} else {
			console.log("📋 DEBUG: WebSocket not ready, can't request config");
		}
	}
	
	announceToScreenReader(`Switched to ${tabName} tab`);
}

// Connection status management
function updateConnectionStatus(connected) {
	const statusIndicator = document.querySelector('.status-indicator');
	const statusText = document.querySelector('.status-text');
	const connectionStat = document.getElementById('connection-stat');
	const pttButton = document.getElementById('ptt-button');
	const messageInput = document.getElementById('message-input');
	const sendButton = document.querySelector('.send-button');
	
	if (connected) {
		statusIndicator.className = 'status-indicator connected';
		statusText.textContent = 'Connected';
		connectionStat.textContent = 'ONLINE';
		connectionStat.style.color = 'var(--success-color)';
		
		// Enable chat controls
		pttButton.disabled = false;
		messageInput.disabled = false;
		sendButton.disabled = false;
		messageInput.placeholder = 'Type your message...';
	} else {
		statusIndicator.className = 'status-indicator disconnected';
		statusText.textContent = 'Disconnected';
		connectionStat.textContent = 'OFFLINE';
		connectionStat.style.color = 'var(--error-color)';
		currentStation = 'DISCONNECTED';
		document.getElementById('current-station').textContent = currentStation;
		
		// Disable chat controls
		pttButton.disabled = true;
		messageInput.disabled = true;
		sendButton.disabled = true;
		messageInput.placeholder = 'Connect to radio system to send messages...';
		
		// Reset PTT state
		if (pttActive) {
			handlePTTStateChange(false);
		}
	}
}

// Message handling
function loadMessageHistory(messages) {
	const messageHistory = document.getElementById('message-history');
	
	// Keep welcome message
	const welcomeMessage = messageHistory.querySelector('.message.system');
	messageHistory.innerHTML = '';
	if (welcomeMessage) {
		messageHistory.appendChild(welcomeMessage);
	}
	
	// Add all messages from history
	messages.forEach(messageData => {
		let direction = 'incoming';
		let from = messageData.from;
		
		if (messageData.from === currentStation || messageData.direction === 'outgoing') {
			direction = 'outgoing';
			from = 'You';
		}
		
		const message = createMessageElement(
			messageData.content,
			direction,
			from,
			messageData.timestamp
		);
		messageHistory.appendChild(message);
	});
	
	scrollToBottom(messageHistory);
	addLogEntry(`Loaded ${messages.length} messages from history`, 'info');
}

function handleIncomingMessage(data) {
	const messageHistory = document.getElementById('message-history');
	
	// Don't display if this is our own message
	if (data.from === currentStation) {
		return;
	}
	
	const message = createMessageElement(data.content, 'incoming', data.from, data.timestamp);
	messageHistory.appendChild(message);
	scrollToBottom(messageHistory);
	
	messageCount.received++;
	document.getElementById('messages-received').textContent = messageCount.received;
	
	announceToScreenReader(`New message from ${data.from}: ${data.content}`);
	addLogEntry(`Message received from ${data.from}`, 'info');
}

function createMessageElement(content, direction, from, timestamp) {
	const messageEl = document.createElement('div');
	messageEl.className = `message ${direction}`;
	messageEl.setAttribute('role', 'log');
	messageEl.setAttribute('aria-live', 'polite');
	
	const contentEl = document.createElement('div');
	contentEl.className = 'message-content';
	contentEl.textContent = content;
	messageEl.appendChild(contentEl);
	
	const metaEl = document.createElement('div');
	metaEl.className = 'message-meta';
	
	const fromEl = document.createElement('span');
	fromEl.className = 'message-from';
	fromEl.textContent = direction === 'outgoing' ? 'You' : from;
	metaEl.appendChild(fromEl);
	
	const timeEl = document.createElement('span');
	timeEl.className = 'message-time';
	const date = new Date(timestamp);
	timeEl.textContent = date.toLocaleTimeString();
	timeEl.setAttribute('title', date.toLocaleString());
	metaEl.appendChild(timeEl);
	
	messageEl.appendChild(metaEl);
	return messageEl;
}

function scrollToBottom(element, smooth = true) {
	if (smooth) {
		element.scrollTo({
			top: element.scrollHeight,
			behavior: 'smooth'
		});
	} else {
		element.scrollTop = element.scrollHeight;
	}
}

// Message sending
function sendMessage() {
	const messageInput = document.getElementById('message-input');
	const message = messageInput.value.trim();
	
	if (!message) return;
	
	if (ws && ws.readyState === WebSocket.OPEN) {
		const timestamp = new Date().toISOString();
		displayOutgoingMessage(message, timestamp);
		
		sendWebSocketMessage('send_text_message', { message });
		messageInput.value = '';
		messageInput.style.height = 'auto';
		
		addLogEntry(`Sent message: ${message.substring(0, 50)}...`, 'info');
	} else {
		showNotification('Cannot send message: not connected', 'error');
	}
}

function displayOutgoingMessage(content, timestamp) {
	const messageHistory = document.getElementById('message-history');
	const message = createMessageElement(content, 'outgoing', currentStation, timestamp);
	messageHistory.appendChild(message);
	scrollToBottom(messageHistory);
	
	messageCount.sent++;
	document.getElementById('messages-sent').textContent = messageCount.sent;
	
	announceToScreenReader(`You sent: ${content}`);
}

// PTT functionality
function togglePTT() {
	if (pttActive) {
		deactivatePTT();
	} else {
		activatePTT();
	}
}

function activatePTT() {
	if (pttActive || !ws || ws.readyState !== WebSocket.OPEN) return;
	
	sendWebSocketMessage('ptt_pressed');
	handlePTTStateChange(true);
	addLogEntry('PTT activated', 'info');
}

function deactivatePTT() {
	if (!pttActive) return;
	
	sendWebSocketMessage('ptt_released');
	handlePTTStateChange(false);
	addLogEntry('PTT released', 'info');
}

function handlePTTStateChange(active) {
	pttActive = active;
	const pttButton = document.getElementById('ptt-button');
	const pttText = pttButton.querySelector('.ptt-text');
	
	if (active) {
		pttButton.classList.add('active');
		pttButton.setAttribute('aria-pressed', 'true');
		pttText.textContent = 'TRANSMITTING';
		announceToScreenReader('PTT activated - transmitting');
	} else {
		pttButton.classList.remove('active');
		pttButton.setAttribute('aria-pressed', 'false');
		pttText.textContent = 'PTT';
		announceToScreenReader('PTT released');
	}
}

// System status management
function updateSystemStatus(data) {
	if (data.station_id) {
		currentStation = data.station_id;
		document.getElementById('current-station').textContent = currentStation;
	}
}

function populateStatusFromData(status) {
	currentStation = status.station_id || 'DISCONNECTED';
	document.getElementById('current-station').textContent = currentStation;
	
	if (status.config) {
		const targetIpElement = document.getElementById('target-ip');
		const targetPortElement = document.getElementById('target-port');
		if (targetIpElement) targetIpElement.value = status.config.target_ip || '';
		if (targetPortElement) targetPortElement.value = status.config.target_port || '';
	}
}

// Logging system
function addLogEntry(message, level = 'info') {
	const logContainer = document.getElementById('system-log');
	const entry = document.createElement('div');
	entry.className = `log-entry ${level}`;
	
	const timestamp = new Date().toLocaleTimeString();
	entry.innerHTML = `<span style="color: var(--text-secondary);">[${timestamp}]</span> ${message}`;
	
	logContainer.appendChild(entry);
	logContainer.scrollTop = logContainer.scrollHeight;
	
	// Limit log entries (keep last 100)
	while (logContainer.children.length > 100) {
		logContainer.removeChild(logContainer.firstChild);
	}
	
	filterLogEntries();
}

function clearLog() {
	document.getElementById('system-log').innerHTML = '';
	addLogEntry('Log cleared', 'info');
}

function filterLogEntries() {
	const selectedLevel = document.getElementById('log-level').value;
	const entries = document.querySelectorAll('.log-entry');
	
	entries.forEach(entry => {
		const entryLevel = entry.className.split(' ')[1];
		let show = false;
		
		switch (selectedLevel) {
			case 'all':
				show = true;
				break;
			case 'info':
				show = ['info', 'success', 'warning', 'error'].includes(entryLevel);
				break;
			case 'warning':
				show = ['warning', 'error'].includes(entryLevel);
				break;
			case 'error':
				show = entryLevel === 'error';
				break;
		}
		
		entry.style.display = show ? 'block' : 'none';
	});
}

// Notification system
function showNotification(message, type = 'info') {
	const notification = document.getElementById('notification');
	notification.textContent = message;
	notification.className = `notification ${type}`;
	
	setTimeout(() => notification.classList.add('show'), 100);
	
	setTimeout(() => {
		notification.classList.remove('show');
	}, 4000);
}

// Accessibility helpers
function announceToScreenReader(message) {
	const announcer = document.getElementById('sr-announcements');
	if (announcer) {
		announcer.textContent = message;
		
		setTimeout(() => {
			announcer.textContent = '';
		}, 1000);
	}
}


// Uptime counter with time formatting
function updateUptime() {
	const elapsed = Date.now() - startTime;
	const totalSeconds = Math.floor(elapsed / 1000);
	
	const days = Math.floor(totalSeconds / 86400);
	const hours = Math.floor((totalSeconds % 86400) / 3600);
	const minutes = Math.floor((totalSeconds % 3600) / 60);
	const seconds = totalSeconds % 60;
	
	const uptimeElement = document.getElementById('uptime');
	if (uptimeElement) {
		let formattedUptime;
		
		if (days > 0) {
			formattedUptime = `${days}d ${hours}h ${minutes}m`;
		} else if (hours > 0) {
			formattedUptime = `${hours}h ${minutes}m ${seconds}s`;
		} else {
			formattedUptime = `${minutes}m ${seconds}s`;
		}
		
		uptimeElement.textContent = formattedUptime;
	}
}





// Manual reconnect function
function attemptReconnect() {
	addLogEntry('Manual reconnection attempt...', 'info');
	reconnectAttempts = 0;
	reconnectDelay = 1000;
	const retryPanel = document.getElementById('connection-retry');
	if (retryPanel) {
		retryPanel.style.display = 'none';
	}
	//connectWebSocket();
	if (window.connectWebSocket) {
		connectWebSocket();
	} else {
		console.log("⚠️ connectWebSocket not yet available");
	}
}

// Auto-uppercase callsign input
function setupSimpleCallsignValidation() {
	const callsignInput = document.getElementById('callsign');
	if (!callsignInput) return;

	// Auto-uppercase on input
	callsignInput.addEventListener('input', function(e) {
		const cursorPosition = e.target.selectionStart;
		e.target.value = e.target.value.toUpperCase();
		e.target.setSelectionRange(cursorPosition, cursorPosition);
	});
}

// Configuration Enter key support
function setupConfigurationEnterKeySupport() {
	// Load Configuration - Enter key support
	const loadInput = document.getElementById('load-config-filename');
	if (loadInput) {
		loadInput.addEventListener('keydown', function(e) {
			if (e.key === 'Enter') {
				e.preventDefault();
				loadConfigFile();
			}
		});
	}

	// Save Configuration - Enter key support
	const saveInput = document.getElementById('save-config-filename');
	if (saveInput) {
		saveInput.addEventListener('keydown', function(e) {
			if (e.key === 'Enter') {
				e.preventDefault();
				saveConfigFile();
			}
		});
	}

	// Create Template Configuration - Enter key support
	const createInput = document.getElementById('create-config-filename');
	if (createInput) {
		createInput.addEventListener('keydown', function(e) {
			if (e.key === 'Enter') {
				e.preventDefault();
				createConfigFileEnhanced();
			}
		});
	}
}

// Initialize reception features
function initializeReceptionFeatures() {
	// Add reception statistics display
	addReceptionStatsDisplay();
	
	// Set up audio streaming if enabled
	setupAudioStreaming();
	
	addLogEntry('Reception features initialized', 'info');
}

function addReceptionStatsDisplay() {
	// Add reception stats to the status panel
	const statusPanel = document.querySelector('.panel:last-child .status-grid');
	if (statusPanel) {
		const receptionStats = document.createElement('div');
		receptionStats.className = 'stat-item';
		receptionStats.innerHTML = `
			<span class="stat-label">Audio Frames Received</span>
			<span id="audio-received-count" class="stat-value">0</span>
		`;
		statusPanel.appendChild(receptionStats);
		
		const lastAudioStat = document.createElement('div');
		lastAudioStat.className = 'stat-item';
		lastAudioStat.innerHTML = `
			<span class="stat-label">Last Audio From</span>
			<span id="last-audio-info" class="stat-value">None</span>
		`;
		statusPanel.appendChild(lastAudioStat);
	}
}

function setupAudioStreaming() {
	// Set up audio streaming checkbox handler
	const streamingCheckbox = document.getElementById('enable-audio-streaming');
	if (streamingCheckbox) {
		streamingCheckbox.addEventListener('change', function() {
			if (this.checked) {
				if (!audioContext && !initializeWebAudio()) {
					this.checked = false;
					showNotification('Cannot enable streaming - audio not available', 'error');
					return;
				}
				addLogEntry('Audio streaming enabled', 'info');
				sendWebSocketMessage('get_audio_stream');
			} else {
				addLogEntry('Audio streaming disabled', 'info');
			}
		});
	}
}

// Update reception statistics
function updateReceptionStats(stats) {
	console.log('📊 Reception stats:', stats);
	
	// Update counters
	if (stats.receiver_stats) {
		const receiverStats = stats.receiver_stats;
		
		// Update existing stats or create new display
		updateStatDisplay('audio-packets-received', receiverStats.audio_packets || 0);
		updateStatDisplay('text-packets-received', receiverStats.text_packets || 0);
		updateStatDisplay('total-packets-received', receiverStats.total_packets || 0);
	}
	
	// Update audio message count
	updateStatDisplay('audio-messages-stored', stats.audio_messages_stored || 0);
}

// Update individual stat display
function updateStatDisplay(statId, value) {
	const statElement = document.getElementById(statId);
	if (statElement) {
		statElement.textContent = value;
	}
}

// Update audio reception statistics
function updateAudioReceptionStats(audioData) {
	// Update audio reception counter
	const audioCounter = document.getElementById('audio-received-count');
	if (audioCounter) {
		const current = parseInt(audioCounter.textContent) || 0;
		audioCounter.textContent = current + 1;
	}
	
	// Update last received audio info
	const lastAudioInfo = document.getElementById('last-audio-info');
	if (lastAudioInfo) {
		const time = new Date(audioData.timestamp).toLocaleTimeString();
		lastAudioInfo.textContent = `${audioData.from_station} at ${time}`;
	}
}

// Event listeners setup
function setupEventListeners() {
	// Message form handling
	const messageForm = document.getElementById('message-form');
	const messageInput = document.getElementById('message-input');
	
	if (messageForm) {
		messageForm.addEventListener('submit', function(e) {
			e.preventDefault();
			sendMessage();
		});
	}

	if (messageInput) {
		messageInput.addEventListener('keydown', function(e) {
			if (e.key === 'Enter' && !e.shiftKey) {
				e.preventDefault();
				sendMessage();
			}
		});

		// Auto-resize textarea
		messageInput.addEventListener('input', function() {
			this.style.height = 'auto';
			this.style.height = Math.min(this.scrollHeight, 100) + 'px';
		});
	}

	// PTT button handling
	const pttButton = document.getElementById('ptt-button');
	if (pttButton) {
		pttButton.addEventListener('click', function() {
			if (!ws || ws.readyState !== WebSocket.OPEN) {
				showNotification('Cannot use PTT: not connected', 'error');
				return;
			}
			togglePTT();
		});
	}

	// Keyboard PTT (spacebar)
	document.addEventListener('keydown', function(e) {
		if (e.code === 'Space' && e.target.tagName !== 'INPUT' && e.target.tagName !== 'TEXTAREA') {
			e.preventDefault();
			if (!pttActive && ws && ws.readyState === WebSocket.OPEN) {
				activatePTT();
			}
		}
	});

	document.addEventListener('keyup', function(e) {
		if (e.code === 'Space' && e.target.tagName !== 'INPUT' && e.target.tagName !== 'TEXTAREA') {
			e.preventDefault();
			if (pttActive) {
				deactivatePTT();
			}
		}
	});

	// Log level filter
	const logLevelSelect = document.getElementById('log-level');
	if (logLevelSelect) {
		logLevelSelect.addEventListener('change', filterLogEntries);
	}

	// Keyboard shortcuts
	document.addEventListener('keydown', function(e) {
		// Ctrl+1 for Chat tab
		if (e.ctrlKey && e.key === '1') {
			e.preventDefault();
			switchTab('chat');
		}
		
		// Ctrl+2 for Config tab
		if (e.ctrlKey && e.key === '2') {
			e.preventDefault();
			switchTab('config');
		}
		
		// Escape to release PTT
		if (e.key === 'Escape' && pttActive) {
			e.preventDefault();
			deactivatePTT();
		}
	});
}

// Handle page visibility for WebSocket reconnection
function setupPageVisibilityHandler() {
	document.addEventListener('visibilitychange', function() {
		if (!document.hidden && (!ws || ws.readyState !== WebSocket.OPEN)) {
			addLogEntry('Page became visible - checking connection', 'info');
			//connectWebSocket();
			if (window.connectWebSocket) {
				connectWebSocket();
			} else {
				console.log("⚠️ connectWebSocket not yet available");
			}
		}
	});
}

// DOM Content Loaded initialization
document.addEventListener('DOMContentLoaded', function() {
	// Initialize features
	initializeReceptionFeatures();
	setupEventListeners();
	setupSimpleCallsignValidation();
	setupConfigurationEnterKeySupport();
	setupPageVisibilityHandler();
	
	// Start uptime counter
	setInterval(updateUptime, 1000);
	
	// Initialize connection
	addLogEntry('Starting Opulent Voice Web Interface', 'info');
	//connectWebSocket();
	if (window.connectWebSocket) {
		connectWebSocket();
	} else {
		console.log("⚠️ connectWebSocket not yet available");
	}
});

// Make functions globally available
window.radioInterface = {
	connectWebSocket,
	sendWebSocketMessage,
	switchTab,
	sendMessage,
	togglePTT,
	showNotification,
	addLogEntry,
	attemptReconnect,
	initializeReceptionFeatures
};
