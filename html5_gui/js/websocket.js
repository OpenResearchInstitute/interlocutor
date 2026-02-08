// WebSocket Communication Management

// WebSocket connection variables 
if (typeof ws === 'undefined') {
    var ws = null;
}
let reconnectAttempts = 0;
let reconnectDelay = 1000;
let maxReconnectAttempts = 10;









// Robust WebSocket connection management
function connectWebSocket() {
    // STEP 1: Complete cleanup of existing connection
    if (ws) {
        // Remove all event handlers to prevent leaks
        ws.onopen = null;
        ws.onclose = null;
        ws.onmessage = null;
        ws.onerror = null;
        
        // Close connection if still open
        if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
            ws.close(1000, "Reconnecting");
        }
        
        ws = null;
    }
    
    // STEP 2: Clear any pending reconnection timers
    if (window.reconnectTimer) {
        clearTimeout(window.reconnectTimer);
        window.reconnectTimer = null;
    }
    
    const wsUrl = `ws://${window.location.host}/ws`;
    addLogEntry(`Attempting to connect to ${wsUrl}`, 'info');
    
    try {
        ws = new WebSocket(wsUrl);
        
        // STEP 3: Set connection timeout
        const connectionTimeout = setTimeout(() => {
            if (ws && ws.readyState === WebSocket.CONNECTING) {
                addLogEntry('Connection timeout - retrying...', 'warning');
                ws.close(1000, "Timeout");
            }
        }, 5000);

        ws.onopen = function(event) {
            console.log(`✅ ${new Date().toISOString()}: WebSocket OPENED successfully`);
            
            clearTimeout(connectionTimeout);
            reconnectAttempts = 0;
            reconnectDelay = 1000;
            
            updateConnectionStatus(true);
            showNotification('Connected to Opulent Voice System', 'success');
            addLogEntry('WebSocket connection established', 'success');
            
            // Hide retry panel if visible
            const retryPanel = document.getElementById('connection-retry');
            if (retryPanel) {
                retryPanel.style.display = 'none';
            }
            
            // Load initial data
            loadCurrentConfig();
            sendWebSocketMessage('get_message_history');
        };

        ws.onclose = function(event) {
            console.log(`🔌 ${new Date().toISOString()}: WebSocket CLOSED, code: ${event.code}, reason: '${event.reason}', wasClean: ${event.wasClean}`);
            
            clearTimeout(connectionTimeout);
            updateConnectionStatus(false);
            
            // STEP 4: Implement connection failure tracking
            if (!window.connectionFailures) {
                window.connectionFailures = 0;
            }
            window.connectionFailures++;
            
            // STEP 5: Auto-refresh after too many failures
            if (window.connectionFailures >= 5) {
                addLogEntry('Too many connection failures - refreshing page...', 'warning');
                showNotification('Connection unstable - refreshing page...', 'warning');
                setTimeout(() => {
                    window.location.reload();
                }, 2000);
                return;
            }
            
            // Only attempt reconnect if it wasn't a clean close
            if (event.code !== 1000 && reconnectAttempts < maxReconnectAttempts) {
                addLogEntry(`Connection closed (code: ${event.code}). Reconnecting in ${reconnectDelay/1000}s... (attempt ${reconnectAttempts + 1}/${maxReconnectAttempts})`, 'warning');
                
                // STEP 6: Store timer reference for cleanup
                window.reconnectTimer = setTimeout(() => {
                    reconnectAttempts++;
                    reconnectDelay = Math.min(reconnectDelay * 1.5, 30000);
                    connectWebSocket();
                }, reconnectDelay);
            } else {
                addLogEntry('Connection failed - maximum retry attempts reached', 'error');
                showNotification('Connection failed. Check if the radio system is running.', 'error');
                const retryPanel = document.getElementById('connection-retry');
                if (retryPanel) {
                    retryPanel.style.display = 'block';
                }
            }
        };

        ws.onmessage = function(event) {
            try {
                const message = JSON.parse(event.data);
                console.log(`📨 ${new Date().toISOString()}: Received ${message.type} message`);
                
                // STEP 7: Reset failure counter on successful message
                window.connectionFailures = 0;
                
                handleWebSocketMessage(message);
            } catch (e) {
                addLogEntry(`Error parsing message: ${e.message}`, 'error');
            }
        };

        ws.onerror = function(error) {
            clearTimeout(connectionTimeout);
            addLogEntry('WebSocket error occurred', 'error');
            updateConnectionStatus(false);
        };

    } catch (error) {
        addLogEntry(`Failed to create WebSocket: ${error.message}`, 'error');
        updateConnectionStatus(false);
    }
}


















function sendWebSocketMessage(action, data = {}) {
	if (ws && ws.readyState === WebSocket.OPEN) {
		try {
			const message = JSON.stringify({ action, data });
			ws.send(message);
			addLogEntry(`Sent: ${action}`, 'info');
			return true;
		} catch (error) {
			addLogEntry(`Error sending message: ${error.message}`, 'error');
			return false;
		}
	} else {
		addLogEntry('Cannot send message - not connected', 'warning');
		return false;
	}
}

// Enhanced WebSocket message handler with transmission grouping
function handleWebSocketMessage(message) {
	switch (message.type) {
		case 'initial_status':
			populateStatusFromData(message.data);
			if (message.data.message_history) {
				loadMessageHistory(message.data.message_history);
			}
			break;
			
		case 'message_received':
			handleIncomingMessage(message.data);
			break;
			
		case 'message_sent':
			addLogEntry('Message confirmed sent', 'success');
			break;
			
		case 'message_history':
			loadMessageHistory(message.data);
			break;
			
		case 'ptt_state_changed':
			handlePTTStateChange(message.data.active);
			break;
			
		case 'status_update':
			updateSystemStatus(message.data);
			break;
			
		case 'error':
			showNotification(message.message || 'An error occurred', 'error');
			addLogEntry(`Error: ${message.message}`, 'error');
			break;
			
		// Enhanced config messages
		case 'config_loaded':
		case 'config_saved':
		case 'config_updated':
		case 'config_created':
		case 'config_not_found':
		case 'config_validation_warning':
		case 'connection_test_result':
		case 'connection_test_with_form_result':
			handleEnhancedConfigMessage(message);
			break;
			
		case 'control_received':
			console.log('🎛️ Control message received:', message.data);
			handleControlMessage(message.data);
			break;
			
		case 'audio_received':
			console.log('🎤 Audio packet received:', message.data);
			handleReceivedAudioPacket(message.data);
			break;

		case 'transmission_started':
			console.log('📡 TRANSMISSION: Received transmission_started');
			const startData = message.data;
			startNewTransmissionFromServer(startData.station_id, startData.start_time, startData.transmission_id);
			break;
		
		case 'transmission_ended':
			console.log('📡 TRANSMISSION: Received transmission_ended');
			const endData = message.data;
			endTransmissionFromServer(endData.station_id, endData.end_time, endData.transmission_id);
			break;

		case 'transmission_audio_data':
			console.log('🎵 TRANSMISSION AUDIO: Received actual audio data');
			handleTransmissionAudioData(message.data);
			break;
			
		case 'audio_stream_data':
			handleAudioStreamData(message.data);
			break;
			
		case 'audio_playback_data':
			console.log('🎵 JS AUDIO PLAYBACK RESPONSE: Server responded with audio data');
			console.log('   Audio data:', message.data);
			handleAudioPlaybackData(message.data);
			break;

		case 'command_result':
			handleCommandResult(message.data);
			break;

		case 'reception_stats':
			updateReceptionStats(message.data);
			break;

		case 'transmission_playback_started':
			console.log('🎵 OPTION A SUCCESS: Transmission playback started via CLI speakers');
			const playbackData = message.data;
	
			// Update ONLY the specific transmission button
			const transmissionId = playbackData.transmission_id;
			if (transmissionId) {
				const transmissionButton = document.querySelector(`[data-transmission-id="${transmissionId}"] .audio-play-btn`);
				if (transmissionButton) {
					// Set to playing state
					transmissionButton.textContent = '🔊 Playing via CLI speakers...';
					transmissionButton.disabled = true;
					console.log(`🔧 Updated transmission button ${transmissionId} to playing state`);
			
					// Re-enable after duration plus buffer - FIXED: Always reset to proper text
					setTimeout(() => {
						transmissionButton.textContent = '▶️ Replay';  // ← Always reset to this
						transmissionButton.disabled = false;
						console.log(`🔧 Reset transmission button ${transmissionId} to ready state`);
					}, playbackData.duration_ms + 1000);
				} else {
					console.warn(`⚠️ Could not find transmission button for playback response ${transmissionId}`);
				}
			}
	
			// Show detailed success notification
			const duration = (playbackData.duration_ms / 1000).toFixed(1);
			const deviceInfo = `device ${playbackData.device_index}`;
			const queueInfo = playbackData.queue_size > 0 ? ` [${playbackData.queue_size} in queue]` : '';
			const bytesInfo = playbackData.audio_bytes ? ` (${(playbackData.audio_bytes/1024).toFixed(1)}KB)` : '';
	
			showNotification(`🔊 Playing ${playbackData.from_station} via CLI speakers (${deviceInfo}) - ${duration}s${queueInfo}`, 'success');
			addLogEntry(`✅ CLI playback: ${playbackData.from_station} → ${deviceInfo} (${playbackData.total_segments} segments)${bytesInfo}`, 'success');
			break;

		case 'transmission_playback_error':
			console.log('🎵 OPTION A ERROR: Transmission playback failed');
			const errorData = message.data;
	
			// Re-enable button with proper text
			if (errorData.transmission_id) {
				const button = document.querySelector(`[data-transmission-id="${errorData.transmission_id}"] .audio-play-btn`);
				if (button) {
					button.textContent = '▶️ Replay';  // ← Always reset to this
					button.disabled = false;
				}
			}
	
			showNotification(`❌ CLI playback failed: ${errorData.error}`, 'error');
			addLogEntry(`❌ CLI playback error: ${errorData.error}`, 'error');
			break;

		case 'outgoing_transmission_started':
			console.log('📤 OUTGOING: Received outgoing_transmission_started');
			const outStartData = message.data;
			startNewOutgoingTransmission(outStartData.station_id, outStartData.start_time, outStartData.transmission_id);
			break;

		case 'outgoing_transmission_ended':
			console.log('📤 OUTGOING: Received outgoing_transmission_ended');
			const outEndData = message.data;
			endOutgoingTransmission(outEndData.station_id, outEndData.end_time, outEndData.transmission_id);
			break;

		case 'outgoing_audio_received':
			console.log('📤 OUTGOING AUDIO: Received outgoing audio packet');
			handleOutgoingAudioPacket(message.data);
			break;

		case 'transcription_received':
			handleTranscriptionReceived(message.data);
			break;

		// Future Enhancement
		// This adds  a handler for accessibility announcements
		// in order to coordinate between Python and JavaScript.
		case 'accessibility_announcement':
			if (typeof accessibilityAnnouncer !== 'undefined') {
				const data = message.data;
				if (data.type === 'newMessage') {
					accessibilityAnnouncer.announceNewMessage(data.from, data.message);
				}
			}
			break;

		default:
			// Try enhanced config handler for any unhandled messages
			handleEnhancedConfigMessage(message);

			// Only log as unknown if it's NOT a config-related message
			if (!message.type.includes('config') && 
			    !message.type.includes('connection_test') && 
			    !message.type.includes('tts_test_result')) {
				console.warn('🔍 Unknown message type:', message.type);
				addLogEntry(`Unknown message type: ${message.type}`, 'warning');
			}
			break;
	}
}

// Handle PTT control messages to define transmission boundaries
function handleControlMessage(controlData) {
	const stationId = controlData.from;
	const controlMessage = controlData.content;
	const timestamp = controlData.timestamp;
	
	console.log(`🎛️ JS CONTROL DEBUG: Control received from ${stationId}: ${controlMessage}`);
	
	if (controlMessage === 'PTT_START') {
		console.log(`🎛️ JS CONTROL DEBUG: Starting transmission for ${stationId}`);
		startNewTransmission(stationId, timestamp);
	} else if (controlMessage === 'PTT_STOP') {
		console.log(`🎛️ JS CONTROL DEBUG: Ending transmission for ${stationId}`);
		endTransmission(stationId, timestamp);
	}
}

// Handle audio stream data
function handleAudioStreamData(streamData) {
	console.log('📊 Audio stream data:', streamData);
	
	if (streamData.audio_available && streamData.packets > 0) {
		addLogEntry(`Audio stream: ${streamData.packets} packets available`, 'info');
		
		// Request audio stream periodically if enabled
		const streamingCheckbox = document.getElementById('enable-audio-streaming');
		if (streamingCheckbox && streamingCheckbox.checked) {
			setTimeout(() => {
				sendWebSocketMessage('get_audio_stream');
			}, 100);
		}
	}
}

// Handle audio playback data from server
function handleAudioPlaybackData(audioData) {
	console.log('🎵 Audio playback data:', audioData);
	
	// Check if this is transmission playback or individual audio playback
	if (audioData.transmission_id) {
		console.log('🎵 TRANSMISSION PLAYBACK: Received transmission playback data');
		console.log(`   Transmission ID: ${audioData.transmission_id}`);
		console.log(`   Total segments: ${audioData.total_segments || 1}`);
		
		// Find the transmission UI element
		const transmissionElement = document.querySelector(`[data-transmission-id="${audioData.transmission_id}"]`);
		if (transmissionElement) {
			const playButton = transmissionElement.querySelector('.audio-play-btn');
			if (playButton) {
				playButton.textContent = '🔊 Playing Transmission...';
				playButton.disabled = true;
				
				// Re-enable after estimated duration
				setTimeout(() => {
					playButton.textContent = '▶️ Replay';
					playButton.disabled = false;
				}, audioData.duration_ms || 2000);
			}
		}
		
		showNotification(`🎵 Playing transmission from ${audioData.from_station} (${audioData.total_segments} segments)`, 'info');
		
	} else {
		// Individual audio playback (existing logic)
		const audioElement = document.querySelector(`[data-audio-id="${audioData.audio_id}"]`);
		if (audioElement) {
			const playButton = audioElement.querySelector('.audio-play-btn');
			if (playButton) {
				playButton.textContent = '⏸️ Playing...';
				playButton.disabled = true;
				
				// Re-enable after estimated duration
				setTimeout(() => {
					playButton.textContent = '▶️ Play Audio';
					playButton.disabled = false;
				}, audioData.duration_ms || 2000);
			}
		}
		
		showNotification(`Playing audio from ${audioData.from_station}`, 'info');
	}
	
	// Note: Actual audio data streaming would require additional implementation
	// For now, we'll show a visual indication that audio is "playing"
	addLogEntry(`Audio playback started: ${audioData.duration_ms}ms`, 'info');
}



// Make connectWebSocket globally accessible
window.connectWebSocket = connectWebSocket;
