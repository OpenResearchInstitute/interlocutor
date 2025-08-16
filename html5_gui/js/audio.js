// Audio Processing and Transmission Management

// TRANSMISSION-BASED storage for GUI
let activeTransmissions = new Map(); // station_id -> current transmission data
let completedTransmissions = []; // List of complete transmissions

// Outgoing transmission storage
let activeOutgoingTransmissions = new Map(); // station_id -> current outgoing transmission data
let completedOutgoingTransmissions = []; // List of complete outgoing transmissions

let maxCompletedTransmissions = 50; // Store last 50 complete transmissions

// Keep individual packets for live audio only (small buffer)
let liveAudioPackets = {}; // For real-time streaming
let maxLivePackets = 200; // Small buffer for live audio

// Global audio context for web audio
let audioContext = null;
let audioQueue = [];
let isPlayingAudio = false;

// Transmission management globals
let transmissionTimeoutMs = 3000; // 3 seconds timeout for incomplete transmissions
let maxTransmissions = 50; // Keep last 50 transmissions

// Initialize Web Audio API
function initializeWebAudio() {
	try {
		// Create audio context (user interaction required)
		audioContext = new (window.AudioContext || window.webkitAudioContext)();
		addLogEntry('Web Audio initialized', 'success');
		return true;
	} catch (error) {
		addLogEntry(`Web Audio initialization failed: ${error.message}`, 'error');
		return false;
	}
}

// Show audio permission request
function showAudioPermissionRequest() {
	const existingRequest = document.getElementById('audio-permission-request');
	if (existingRequest) return;
	
	const permissionDiv = document.createElement('div');
	permissionDiv.id = 'audio-permission-request';
	permissionDiv.className = 'audio-permission-request';
	permissionDiv.innerHTML = `
		<div class="permission-content">
			<h3>🎤 Audio Reception Available</h3>
			<p>Click to enable audio playback for received voice messages</p>
			<button onclick="enableAudioReception()" class="btn btn-primary">
				Enable Audio
			</button>
			<button onclick="dismissAudioRequest()" class="btn">
				Not Now
			</button>
		</div>
	`;
	
	document.body.appendChild(permissionDiv);
}

// Enable audio reception
function enableAudioReception() {
	if (initializeWebAudio()) {
		showNotification('Audio reception enabled', 'success');
		dismissAudioRequest();
		
		// Request any pending audio
		sendWebSocketMessage('get_audio_stream');
	} else {
		showNotification('Failed to enable audio - check browser permissions', 'error');
	}
}

// Dismiss audio permission request
function dismissAudioRequest() {
	const request = document.getElementById('audio-permission-request');
	if (request) {
		request.remove();
	}
}

// Start a new transmission for a station
function startNewTransmission(stationId, startTime) {
	console.log(`🎤 📋 Starting transmission from ${stationId}`);
	
	// End any previous incomplete transmission from this station
	if (activeTransmissions.has(stationId)) {
		console.log(`⚠️ Force-ending previous incomplete transmission from ${stationId}`);
		endTransmission(stationId, new Date().toISOString(), true);
	}
	
	const transmission = {
		stationId: stationId,
		startTime: startTime,
		endTime: null,
		audioPackets: [],
		totalDuration: 0,
		firstPacketTime: null,
		lastPacketTime: null,
		transmissionId: `tx_${stationId}_${Date.now()}`,
		incomplete: true,
		timeoutId: null
	};
	
	activeTransmissions.set(stationId, transmission);
	addLogEntry(`📡 Transmission started: ${stationId}`, 'success');
	
	// Show temporary indicator
	showNotification(`📻 ${stationId} started transmitting`, 'info');
}

// End a transmission and create UI bubble
function endTransmission(stationId, endTime, forced = false) {
	const transmission = activeTransmissions.get(stationId);
	if (!transmission) {
		console.log(`⚠️ Tried to end transmission for ${stationId} but none active`);
		return;
	}
	
	// Clear timeout
	if (transmission.timeoutId) {
		clearTimeout(transmission.timeoutId);
	}
	
	transmission.endTime = endTime;
	transmission.incomplete = false;
	
	console.log(`🎤 📋 Ending transmission from ${stationId}:`);
	console.log(`   Packets: ${transmission.audioPackets.length}`);
	console.log(`   Duration: ${transmission.totalDuration}ms`);
	console.log(`   Forced: ${forced}`);
	
	// Move to completed transmissions
	completedTransmissions.push(transmission);
	activeTransmissions.delete(stationId);
	
	// Limit stored transmissions
	if (completedTransmissions.length > maxTransmissions) {
		completedTransmissions = completedTransmissions.slice(-maxTransmissions);
	}
	
	// Create UI bubble for the complete transmission
	if (transmission.audioPackets.length > 0) {
		createTransmissionUIBubble(transmission);
		const duration = (transmission.totalDuration / 1000).toFixed(1);
		addLogEntry(`📻 Transmission completed: ${stationId} (${transmission.audioPackets.length} packets, ${duration}s)`, 'success');
		showNotification(`📻 ${stationId} transmission complete (${duration}s)`, 'success');
	} else {
		console.log(`⚠️ No audio packets in transmission from ${stationId}`);
		addLogEntry(`⚠️ Empty transmission from ${stationId}`, 'warning');
	}
}

// Handle individual audio packets and add to active transmission
function handleReceivedAudioPacket(audioData) {
	const stationId = audioData.from_station;
	
	console.log(`🎤 Audio packet from ${stationId}: ${audioData.duration_ms}ms`);
	
	// Get active transmission
	let transmission = activeTransmissions.get(stationId);
	
	if (!transmission) {
		// No active transmission - start one automatically (fallback for missing PTT_START)
		console.log(`🎤 ⚠️ Auto-starting transmission for ${stationId} (no PTT_START received)`);
		startNewTransmission(stationId, audioData.timestamp);
		transmission = activeTransmissions.get(stationId);
	}
	
	// Add packet to transmission
	transmission.audioPackets.push(audioData);
	transmission.totalDuration += audioData.duration_ms;
	transmission.lastPacketTime = audioData.timestamp;
	
	if (!transmission.firstPacketTime) {
		transmission.firstPacketTime = audioData.timestamp;
	}
	
	// Reset auto-timeout for this transmission
	resetTransmissionTimeout(stationId);
	
	// Continue real-time audio playback (don't interfere with live audio)
	playLiveAudio(audioData);
	
	console.log(`🎤 Added packet to transmission ${transmission.transmissionId} (${transmission.audioPackets.length} packets, ${transmission.totalDuration}ms total)`);
}

// Auto-timeout incomplete transmissions (fallback for missing PTT_STOP)
function resetTransmissionTimeout(stationId) {
	const transmission = activeTransmissions.get(stationId);
	if (!transmission) return;
	
	// Clear existing timeout
	if (transmission.timeoutId) {
		clearTimeout(transmission.timeoutId);
	}
	
	// Set new timeout
	transmission.timeoutId = setTimeout(() => {
		console.log(`⏰ Auto-ending transmission from ${stationId} (timeout)`);
		endTransmission(stationId, new Date().toISOString(), true);
	}, transmissionTimeoutMs);
}

// Server-based transmission management
function startNewTransmissionFromServer(stationId, startTime, transmissionId) {
	console.log(`📡 SERVER TRANSMISSION START: ${transmissionId} from ${stationId}`);
	
	// End any previous incomplete transmission from this station
	if (activeTransmissions.has(stationId)) {
		console.log(`⚠️ Force-ending previous incomplete transmission from ${stationId}`);
		const oldTransmission = activeTransmissions.get(stationId);
		endTransmissionFromServer(stationId, new Date().toISOString(), oldTransmission.transmissionId);
	}
	
	const transmission = {
		stationId: stationId,
		startTime: startTime,
		endTime: null,
		audioPackets: [],
		totalDuration: 0,
		firstPacketTime: null,
		lastPacketTime: null,
		transmissionId: transmissionId,  // Use server's ID
		incomplete: true,
		timeoutId: null
	};
	
	activeTransmissions.set(stationId, transmission);
	addLogEntry(`📡 Transmission started: ${transmissionId}`, 'success');
	
	// Show temporary indicator
	showNotification(`📻 ${stationId} started transmitting`, 'info');
}

function endTransmissionFromServer(stationId, endTime, transmissionId) {
	const transmission = activeTransmissions.get(stationId);
	if (!transmission) {
		console.log(`⚠️ Tried to end transmission for ${stationId} but none active`);
		return;
	}
	
	// CRITICAL FIX: Update the transmission with server's final ID
	console.log(`📄 ID SYNC: Updating transmission ID from ${transmission.transmissionId} to ${transmissionId}`);
	transmission.transmissionId = transmissionId;
	transmission.endTime = endTime;
	transmission.incomplete = false;
	
	// Clear timeout
	if (transmission.timeoutId) {
		clearTimeout(transmission.timeoutId);
	}
	
	console.log(`📡 TRANSMISSION COMPLETE: ${transmission.transmissionId} - `
				+ `${transmission.audioPackets.length} packets, ${transmission.totalDuration}ms`);
	
	// Move to completed transmissions
	completedTransmissions.push(transmission);
	activeTransmissions.delete(stationId);
	
	// Cleanup old transmissions
	if (completedTransmissions.length > maxTransmissions) {
		completedTransmissions = completedTransmissions.slice(-maxTransmissions);
	}
	
	// Create UI bubble for the complete transmission
	if (transmission.audioPackets.length > 0) {
		createTransmissionUIBubble(transmission);
		const duration = (transmission.totalDuration / 1000).toFixed(1);
		addLogEntry(`📻 Transmission completed: ${stationId} (${transmission.audioPackets.length} packets, ${duration}s)`, 'success');
		showNotification(`📻 ${stationId} transmission complete (${duration}s)`, 'success');
	} else {
		console.log(`⚠️ No audio packets in transmission from ${stationId}`);
		addLogEntry(`⚠️ Empty transmission from ${stationId}`, 'warning');
	}
}

// Outgoing transmission management
function startNewOutgoingTransmission(stationId, startTime, transmissionId) {
	console.log(`📤 OUTGOING START: ${transmissionId} from ${stationId}`);
	
	// End any previous incomplete outgoing transmission
	if (activeOutgoingTransmissions.has(stationId)) {
		console.log(`⚠️ Force-ending previous incomplete outgoing transmission from ${stationId}`);
		const oldTransmission = activeOutgoingTransmissions.get(stationId);
		endOutgoingTransmission(stationId, new Date().toISOString(), oldTransmission.transmissionId);
	}
	
	const transmission = {
		stationId: stationId,
		startTime: startTime,
		endTime: null,
		audioPackets: [],
		totalDuration: 0,
		firstPacketTime: null,
		lastPacketTime: null,
		transmissionId: transmissionId,
		incomplete: true,
		timeoutId: null,
		direction: 'outgoing'
	};
	
	activeOutgoingTransmissions.set(stationId, transmission);
	addLogEntry(`📤 Outgoing transmission started: ${transmissionId}`, 'success');
	
	// Show temporary indicator
	showNotification(`📻 You started transmitting`, 'info');
}

function endOutgoingTransmission(stationId, endTime, transmissionId) {
	const transmission = activeOutgoingTransmissions.get(stationId);
	if (!transmission) {
		console.log(`⚠️ Tried to end outgoing transmission for ${stationId} but none active`);
		return;
	}
	
	// Update transmission with server's final ID
	console.log(`📄 OUTGOING ID SYNC: Updating transmission ID from ${transmission.transmissionId} to ${transmissionId}`);
	transmission.transmissionId = transmissionId;
	transmission.endTime = endTime;
	transmission.incomplete = false;
	
	// Clear timeout
	if (transmission.timeoutId) {
		clearTimeout(transmission.timeoutId);
	}
	
	console.log(`📤 OUTGOING TRANSMISSION COMPLETE: ${transmission.transmissionId} - `
				+ `${transmission.audioPackets.length} packets, ${transmission.totalDuration}ms`);
	
	// Move to completed outgoing transmissions
	completedOutgoingTransmissions.push(transmission);
	activeOutgoingTransmissions.delete(stationId);
	
	// Cleanup old outgoing transmissions
	if (completedOutgoingTransmissions.length > maxTransmissions) {
		completedOutgoingTransmissions = completedOutgoingTransmissions.slice(-maxTransmissions);
	}
	
	// Create UI bubble for the complete outgoing transmission
	if (transmission.audioPackets.length > 0) {
		createTransmissionUIBubble(transmission, 'outgoing');  // NEW: Pass direction
		const duration = (transmission.totalDuration / 1000).toFixed(1);
		addLogEntry(`📻 Outgoing transmission completed: ${stationId} (${transmission.audioPackets.length} packets, ${duration}s)`, 'success');
		showNotification(`📻 Your transmission complete (${duration}s)`, 'success');
	} else {
		console.log(`⚠️ No audio packets in outgoing transmission from ${stationId}`);
		addLogEntry(`⚠️ Empty outgoing transmission from ${stationId}`, 'warning');
	}
}

function handleOutgoingAudioPacket(audioData) {
	const stationId = audioData.from_station;
	
	console.log(`📤 OUTGOING AUDIO: Audio packet from ${stationId}: ${audioData.duration_ms}ms`);
	
	// Get active outgoing transmission
	let transmission = activeOutgoingTransmissions.get(stationId);
	
	if (!transmission) {
		// No active outgoing transmission - this shouldn't happen but handle gracefully
		console.log(`📤 ⚠️ Auto-starting outgoing transmission for ${stationId} (no transmission start received)`);
		startNewOutgoingTransmission(stationId, audioData.timestamp, `tx_out_${stationId}_${Date.now()}`);
		transmission = activeOutgoingTransmissions.get(stationId);
	}
	
	// Add packet to outgoing transmission
	transmission.audioPackets.push(audioData);
	transmission.totalDuration += audioData.duration_ms;
	transmission.lastPacketTime = audioData.timestamp;
	
	if (!transmission.firstPacketTime) {
		transmission.firstPacketTime = audioData.timestamp;
	}
	
	// Reset auto-timeout for this outgoing transmission
	resetOutgoingTransmissionTimeout(stationId);
	
	console.log(`📤 Added packet to outgoing transmission ${transmission.transmissionId} (${transmission.audioPackets.length} packets, ${transmission.totalDuration}ms total)`);
}

function resetOutgoingTransmissionTimeout(stationId) {
	const transmission = activeOutgoingTransmissions.get(stationId);
	if (!transmission) return;
	
	// Clear existing timeout
	if (transmission.timeoutId) {
		clearTimeout(transmission.timeoutId);
	}
	
	// Set new timeout
	transmission.timeoutId = setTimeout(() => {
		console.log(`⏰ Auto-ending outgoing transmission from ${stationId} (timeout)`);
		endOutgoingTransmission(stationId, new Date().toISOString(), transmission.transmissionId);
	}, transmissionTimeoutMs);
}

// Create UI bubble for completed transmission
function createTransmissionUIBubble(transmission, direction = 'incoming') {
	const messageHistory = document.getElementById('message-history');
	const transmissionElement = document.createElement('div');			
	transmissionElement.className = `message ${direction} audio-message`;
	transmissionElement.setAttribute('data-transmission-id', transmission.transmissionId);
	
	const totalDurationSec = (transmission.totalDuration / 1000).toFixed(1);
	const packetCount = transmission.audioPackets.length;
	const startTime = new Date(transmission.startTime).toLocaleTimeString();

	// Different display based on direction
	const displayName = direction === 'outgoing' ? 'You' : transmission.stationId;			

	transmissionElement.innerHTML = `
		<div class="audio-content">
			<div class="audio-controls">
				<button class="audio-play-btn" onclick="playCompleteTransmission('${transmission.transmissionId}')">
					▶️ Replay
				</button>
				<div class="audio-waveform">
					<div class="waveform-bars">
						${'<div class="bar"></div>'.repeat(Math.min(packetCount, 20))}
					</div>
				</div>
			</div>
		</div>
		<div class="message-meta">
			<span>${displayName}</span>
			<span class="transmission-meta">${totalDurationSec}s</span>
			<span>${startTime}</span>
		</div>
	`;
	
	messageHistory.appendChild(transmissionElement);
	scrollToBottom(messageHistory);
	
	// Animate appearance
	transmissionElement.style.opacity = '0';
	transmissionElement.style.transform = 'translateY(20px)';
	setTimeout(() => {
		transmissionElement.style.transition = 'all 0.3s ease';
		transmissionElement.style.opacity = '1';
		transmissionElement.style.transform = 'translateY(0)';
	}, 10);
	
	// Animate waveform bars
	const bars = transmissionElement.querySelectorAll('.bar');
	bars.forEach((bar, index) => {
		const height = Math.random() * 80 + 20; // Random height 20-100%
		setTimeout(() => {
			bar.style.height = `${height}%`;
		}, index * 50);
	});
}

// Play complete transmission
function playCompleteTransmission(transmissionId) {
	console.log(`🎵 TRANSMISSION PLAYBACK: Request for ${transmissionId}`);
	
	// DEBUG: Show what's in storage
	console.log(`🔍 STORAGE DEBUG: Looking for transmission ${transmissionId}`);
	console.log(`🔍 STORAGE DEBUG: Incoming transmissions:`, completedTransmissions.map(t => t.transmissionId));
	console.log(`🔍 STORAGE DEBUG: Outgoing transmissions:`, completedOutgoingTransmissions.map(t => t.transmissionId));
	
	// Search in both incoming and outgoing completed transmissions
	let transmission = completedTransmissions.find(t => t.transmissionId === transmissionId);
	let direction = 'incoming';
	
	if (!transmission) {
		transmission = completedOutgoingTransmissions.find(t => t.transmissionId === transmissionId);
		direction = 'outgoing';
		console.log(`🔍 STORAGE DEBUG: Found in outgoing:`, transmission ? 'YES' : 'NO');
	}
	
	if (!transmission) {
		console.error(`❌ Transmission ${transmissionId} not found in incoming or outgoing`);
		showNotification('Transmission not found', 'error');
		return;
	}
	
	console.log(`🎵 PLAYBACK: Found ${direction} transmission with ${transmission.audioPackets.length} packets`);
	
	// Update button state immediately
	const button = document.querySelector(`[data-transmission-id="${transmissionId}"] .audio-play-btn`);
	if (button) {
		const directionText = direction === 'outgoing' ? 'your own' : transmission.stationId + "'s";
		button.textContent = `⏳ Requesting playback of ${directionText} message...`;
		button.disabled = true;
	}
	
	// Send request to Python backend for CLI speaker playback
	sendWebSocketMessage('request_transmission_playback', { 
		transmission_id: transmissionId,
		station_id: transmission.stationId,
		start_time: transmission.startTime,
		duration_ms: transmission.totalDuration,
		direction: direction  // Include direction in request
	});
	
	const duration = (transmission.totalDuration / 1000).toFixed(1);
	const directionText = direction === 'outgoing' ? 'your own' : transmission.stationId + "'s";
	showNotification(`🎵 Requesting ${directionText} CLI playback (${duration}s)`, 'info');
	addLogEntry(`🎵 CLI playback request: ${directionText} transmission (${duration}s)`, 'info');
}

// Continue real-time audio (don't interfere with live audio)
function playLiveAudio(audioData) {
	// This maintains the existing real-time audio functionality
	// The live audio stream should continue working as before
	
	// Only update statistics, don't create UI bubbles for individual packets
	updateAudioReceptionStats(audioData);
	
	// Continue with existing live audio processing if auto-play is enabled
	const autoPlayCheckbox = document.getElementById('auto-play-audio');
	if (autoPlayCheckbox && autoPlayCheckbox.checked) {
		// Note: Individual packet playback disabled - only transmission playback now
		console.log(`📊 Live audio from ${audioData.from_station} continues playing`);
	}
}

// Handle transmission audio data from server (complex audio processing)
function handleTransmissionAudioData(audioData) {
	console.log('🎵 TRANSMISSION AUDIO: Received actual audio data');
	console.log('   Audio data keys:', Object.keys(audioData));
	console.log('   Sample rate:', audioData.sample_rate);
	console.log('   Channels:', audioData.channels);
	console.log('   Format:', audioData.audio_format);
	console.log('   Data length:', audioData.audio_data ? audioData.audio_data.length : 0, 'chars (base64)');
	
	// Ensure audio context is available
	if (!audioContext) {
		console.log('🎵 TRANSMISSION AUDIO: No audio context - initializing');
		if (!initializeWebAudio()) {
			console.error('🎵 TRANSMISSION AUDIO: Failed to initialize audio context');
			return;
		}
	}
	
	try {
		// Step 1: Decode base64 audio data to binary
		const base64Data = audioData.audio_data;
		if (!base64Data) {
			console.error('🎵 TRANSMISSION AUDIO: No audio data provided');
			return;
		}
		
		// Decode base64 to ArrayBuffer
		const binaryString = atob(base64Data);
		const bytes = new Uint8Array(binaryString.length);
		for (let i = 0; i < binaryString.length; i++) {
			bytes[i] = binaryString.charCodeAt(i);
		}
		
		console.log('🎵 TRANSMISSION AUDIO: Decoded', bytes.length, 'bytes of PCM data');
		
		// Step 2: Convert 16-bit signed PCM to Float32Array
		const sampleRate = audioData.sample_rate || 48000;
		const channels = audioData.channels || 1;
		const pcmSamples = bytes.length / 2; // 16-bit = 2 bytes per sample
		
		// Create Int16Array view of the data
		const pcmInt16 = new Int16Array(bytes.buffer);
		console.log('🎵 TRANSMISSION AUDIO: PCM samples:', pcmInt16.length);
		
		// Convert to Float32Array (Web Audio format)
		const floatSamples = new Float32Array(pcmInt16.length);
		for (let i = 0; i < pcmInt16.length; i++) {
			floatSamples[i] = pcmInt16[i] / 32768.0; // Convert 16-bit to float (-1.0 to 1.0)
		}
		
		console.log('🎵 TRANSMISSION AUDIO: Converted to float samples:', floatSamples.length);
		
		// Step 3: Create Web Audio buffer
		const audioBuffer = audioContext.createBuffer(channels, floatSamples.length, sampleRate);
		
		// Copy float data to audio buffer
		for (let channel = 0; channel < channels; channel++) {
			const channelData = audioBuffer.getChannelData(channel);
			if (channels === 1) {
				// Mono: copy all samples to this channel
				channelData.set(floatSamples);
			} else {
				// Stereo: interleaved samples (not implemented for this use case)
				console.warn('🎵 TRANSMISSION AUDIO: Stereo not implemented');
				channelData.set(floatSamples); // Fallback: copy mono to all channels
			}
		}
		
		console.log('🎵 TRANSMISSION AUDIO: Audio buffer created');
		console.log('   Duration:', audioBuffer.duration.toFixed(3), 'seconds');
		console.log('   Sample rate:', audioBuffer.sampleRate, 'Hz');
		console.log('   Channels:', audioBuffer.numberOfChannels);
		
		// Step 4: Create audio source and play
		const source = audioContext.createBufferSource();
		source.buffer = audioBuffer;
		
		// Connect to speakers
		source.connect(audioContext.destination);
		
		// Add some gain control to prevent clipping
		const gainNode = audioContext.createGain();
		gainNode.gain.value = 0.7; // Reduce volume slightly
		source.connect(gainNode);
		gainNode.connect(audioContext.destination);
		
		// Play the audio
		const startTime = audioContext.currentTime;
		source.start(startTime);
		
		console.log('🎵 TRANSMISSION AUDIO: ✅ PLAYING NOW! Duration:', audioBuffer.duration.toFixed(3), 's');
		
		// Update UI to show playback status
		const transmissionId = audioData.transmission_id;
		if (transmissionId) {
			const button = document.querySelector(`[data-transmission-id="${transmissionId}"] .audio-play-btn`);
			if (button) {
				const originalText = button.textContent;
				button.textContent = '🔊 Playing...';
				button.disabled = true;
				
				// Re-enable button after playback
				setTimeout(() => {
					button.textContent = originalText;
					button.disabled = false;
				}, audioBuffer.duration * 1000 + 100);
			}
		}
		
		// Show success notification
		showNotification(`🔊 Playing ${audioData.from_station} transmission (${audioBuffer.duration.toFixed(1)}s)`, 'success');
		
	} catch (error) {
		console.error('🎵 TRANSMISSION AUDIO: ❌ PLAYBACK ERROR:', error);
		console.error('Error details:', error.stack);
		showNotification(`❌ Audio playback failed: ${error.message}`, 'error');
		
		// Re-enable button on error
		const transmissionId = audioData.transmission_id;
		if (transmissionId) {
			const button = document.querySelector(`[data-transmission-id="${transmissionId}"] .audio-play-btn`);
			if (button) {
				button.textContent = '▶️ Replay';
				button.disabled = false;
			}
		}
	}
}




function handleTranscriptionReceived(transcriptionData) {
    //Handle received transcription data
    try {
        const transmissionId = transcriptionData.transmission_id;
        if (!transmissionId) return;
        
        // Find the corresponding audio message bubble
        const audioElement = document.querySelector(`[data-transmission-id="${transmissionId}"]`);
        if (!audioElement) {
            console.log(`No audio element found for transmission ${transmissionId}`);
            return;
        }
        
        // Add transcription to the audio bubble
        let transcriptionDiv = audioElement.querySelector('.transcription-text');
        if (!transcriptionDiv) {
            transcriptionDiv = document.createElement('div');
            transcriptionDiv.className = 'transcription-text';
            audioElement.querySelector('.audio-content').appendChild(transcriptionDiv);
        }
        
        // Set transcription content with confidence indicator
        const confidencePercent = Math.round(transcriptionData.confidence * 100);
        const confidenceClass = confidencePercent >= 70 ? 'high-confidence' : 'low-confidence';
        
        transcriptionDiv.innerHTML = `
            <div class="transcription-content ${confidenceClass}">
                <span class="transcription-icon">🗨️</span>
                <span class="transcription-message">"${transcriptionData.transcription}"</span>
                <span class="transcription-confidence">(${confidencePercent}%)</span>
            </div>
        `;
        
        console.log(`📝 Added transcription to ${transmissionId}: "${transcriptionData.transcription}"`);
        
    } catch (error) {
        console.error('Error handling transcription:', error);
    }
}

