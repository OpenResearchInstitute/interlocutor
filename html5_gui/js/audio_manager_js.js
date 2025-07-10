/**
 * Audio Manager for Opulent Voice Radio Interface
 * Handles audio message storage, playback, and future transcription
 * Phase 1: Basic structure and placeholder functionality
 */

class AudioManager {
    constructor() {
        // Audio message storage
        this.audioMessages = new Map();
        this.messageOrder = []; // Chronological order for cleanup
        this.maxStoredMessages = 100;
        
        // Playback state
        this.currentlyPlaying = null;
        this.audioContext = null;
        
        // Statistics
        this.stats = {
            messagesStored: 0,
            messagesPlayed: 0,
            oldestMessageTime: null,
            newestMessageTime: null
        };
        
        console.log('AudioManager initialized');
    }
    
    /**
     * Initialize audio context (if needed for future features)
     */
    async initializeAudioContext() {
        try {
            if (!this.audioContext && window.AudioContext) {
                this.audioContext = new AudioContext();
                console.log('Audio context initialized');
            }
        } catch (error) {
            console.warn('Failed to initialize audio context:', error);
        }
    }
    
    /**
     * Add new audio message (Phase 1: metadata only)
     */
    addAudioMessage(messageData) {
        const message = {
            id: messageData.id,
            metadata: {
                from: messageData.metadata.from || 'UNKNOWN',
                timestamp: messageData.timestamp,
                duration: messageData.metadata.duration || 0,
                quality: messageData.metadata.quality_indicator || 'unknown',
                authenticated: messageData.metadata.authenticated || false,
                type: messageData.metadata.message_type || 'voice'
            },
            audioUrl: null, // Will be set in Phase 2
            transcription: null, // Will be set in Phase 3
            waveformData: null, // Future enhancement
            playCount: 0,
            lastPlayed: null,
            created: new Date().toISOString()
        };
        
        // Store message
        this.audioMessages.set(message.id, message);
        this.messageOrder.push(message.id);
        
        // Update statistics
        this.stats.messagesStored++;
        this.stats.newestMessageTime = message.created;
        if (!this.stats.oldestMessageTime) {
            this.stats.oldestMessageTime = message.created;
        }
        
        // Maintain storage limit
        this.maintainStorageLimit();
        
        console.log('Audio message added:', message.id);
        return message;
    }
    
    /**
     * Maintain storage limit by removing oldest messages
     */
    maintainStorageLimit() {
        while (this.messageOrder.length > this.maxStoredMessages) {
            const oldestId = this.messageOrder.shift();
            const oldMessage = this.audioMessages.get(oldestId);
            
            if (oldMessage) {
                // Clean up blob URL if it exists
                if (oldMessage.audioUrl) {
                    URL.revokeObjectURL(oldMessage.audioUrl);
                }
                
                this.audioMessages.delete(oldestId);
                console.log('Removed oldest audio message:', oldestId);
            }
        }
        
        // Update oldest message time
        if (this.messageOrder.length > 0) {
            const oldestMessage = this.audioMessages.get(this.messageOrder[0]);
            this.stats.oldestMessageTime = oldestMessage ? oldestMessage.created : null;
        } else {
            this.stats.oldestMessageTime = null;
        }
    }
    
    /**
     * Get audio message by ID
     */
    getMessage(messageId) {
        return this.audioMessages.get(messageId);
    }
    
    /**
     * Get all audio messages (sorted by timestamp)
     */
    getAllMessages() {
        return this.messageOrder
            .map(id => this.audioMessages.get(id))
            .filter(msg => msg) // Remove any undefined messages
            .sort((a, b) => new Date(a.created) - new Date(b.created));
    }
    
    /**
     * Get messages from specific station
     */
    getMessagesFromStation(callsign) {
        return this.getAllMessages().filter(msg => 
            msg.metadata.from === callsign
        );
    }
    
    /**
     * Play audio message (Phase 1: placeholder)
     */
    async playMessage(messageId) {
        const message = this.audioMessages.get(messageId);
        if (!message) {
            console.warn('Audio message not found:', messageId);
            return false;
        }
        
        console.log('Playing audio message:', messageId);
        
        // Phase 1: Just update statistics and announce
        message.playCount++;
        message.lastPlayed = new Date().toISOString();
        this.stats.messagesPlayed++;
        
        // Phase 1: Simulate playback
        this.currentlyPlaying = messageId;
        
        // Announce to screen reader
        this.announcePlayback(message);
        
        // Simulate playback duration
        const duration = (message.metadata.duration || 5) * 1000;
        setTimeout(() => {
            this.currentlyPlaying = null;
            this.announcePlaybackEnd(message);
        }, duration);
        
        return true;
    }
    
    /**
     * Stop current playback
     */
    stopPlayback() {
        if (this.currentlyPlaying) {
            console.log('Stopping audio playback:', this.currentlyPlaying);
            this.currentlyPlaying = null;
            return true;
        }
        return false;
    }
    
    /**
     * Check if message is currently playing
     */
    isPlaying(messageId) {
        return this.currentlyPlaying === messageId;
    }
    
    /**
     * Get current playback status
     */
    getPlaybackStatus() {
        return {
            playing: this.currentlyPlaying !== null,
            currentMessageId: this.currentlyPlaying,
            currentMessage: this.currentlyPlaying ? this.audioMessages.get(this.currentlyPlaying) : null
        };
    }
    
    /**
     * Search messages by content (future transcription search)
     */
    searchMessages(query) {
        // Phase 1: Search by station callsign only
        const lowercaseQuery = query.toLowerCase();
        
        return this.getAllMessages().filter(msg => {
            const from = msg.metadata.from.toLowerCase();
            return from.includes(lowercaseQuery);
        });
    }
    
    /**
     * Delete specific message
     */
    deleteMessage(messageId) {
        const message = this.audioMessages.get(messageId);
        if (!message) {
            return false;
        }
        
        // Clean up blob URL if it exists
        if (message.audioUrl) {
            URL.revokeObjectURL(message.audioUrl);
        }
        
        // Remove from storage
        this.audioMessages.delete(messageId);
        
        // Remove from order array
        const index = this.messageOrder.indexOf(messageId);
        if (index > -1) {
            this.messageOrder.splice(index, 1);
        }
        
        console.log('Deleted audio message:', messageId);
        return true;
    }
    
    /**
     * Clear all stored messages
     */
    clearAllMessages() {
        // Clean up all blob URLs
        for (const message of this.audioMessages.values()) {
            if (message.audioUrl) {
                URL.revokeObjectURL(message.audioUrl);
            }
        }
        
        this.audioMessages.clear();
        this.messageOrder = [];
        this.currentlyPlaying = null;
        
        // Reset statistics
        this.stats = {
            messagesStored: 0,
            messagesPlayed: this.stats.messagesPlayed, // Keep play count
            oldestMessageTime: null,
            newestMessageTime: null
        };
        
        console.log('All audio messages cleared');
    }
    
    /**
     * Get storage statistics
     */
    getStats() {
        const currentStats = { ...this.stats };
        currentStats.messagesStored = this.audioMessages.size;
        currentStats.storageUsed = this.audioMessages.size;
        currentStats.storageLimit = this.maxStoredMessages;
        currentStats.storagePercent = Math.round((this.audioMessages.size / this.maxStoredMessages) * 100);
        
        return currentStats;
    }
    
    /**
     * Get message count
     */
    getMessageCount() {
        return this.audioMessages.size;
    }
    
    /**
     * Set storage limit
     */
    setStorageLimit(limit) {
        this.maxStoredMessages = Math.max(1, limit);
        this.maintainStorageLimit();
        console.log('Audio storage limit set to:', this.maxStoredMessages);
    }
    
    /**
     * Export message metadata (for backup/debugging)
     */
    exportMetadata() {
        const messages = this.getAllMessages().map(msg => ({
            id: msg.id,
            metadata: msg.metadata,
            playCount: msg.playCount,
            lastPlayed: msg.lastPlayed,
            created: msg.created
        }));
        
        return {
            messages: messages,
            stats: this.getStats(),
            exportTime: new Date().toISOString()
        };
    }
    
    /**
     * Announce playback to screen reader
     */
    announcePlayback(message) {
        const announcement = `Playing audio message from ${message.metadata.from}, ` +
                           `${message.metadata.duration} seconds, ` +
                           `recorded at ${new Date(message.metadata.timestamp).toLocaleTimeString()}`;
        
        this.updateAriaLiveRegion(announcement);
    }
    
    /**
     * Announce playback end to screen reader
     */
    announcePlaybackEnd(message) {
        const announcement = `Finished playing audio message from ${message.metadata.from}`;
        this.updateAriaLiveRegion(announcement);
    }
    
    /**
     * Update ARIA live region for announcements
     */
    updateAriaLiveRegion(message) {
        const liveRegion = document.getElementById('sr-announcements');
        if (liveRegion) {
            liveRegion.textContent = message;
            
            // Clear after delay to allow re-announcement
            setTimeout(() => {
                liveRegion.textContent = '';
            }, 1000);
        }
    }
    
    /**
     * Create audio message element for UI display
     */
    createMessageElement(message) {
        const messageEl = document.createElement('article');
        messageEl.className = 'audio-message';
        messageEl.setAttribute('role', 'article');
        messageEl.setAttribute('data-message-id', message.id);
        
        const time = new Date(message.metadata.timestamp).toLocaleTimeString();
        const duration = message.metadata.duration;
        const isPlaying = this.isPlaying(message.id);
        
        messageEl.innerHTML = `
            <header class="message-header">
                <span class="callsign">${this.escapeHtml(message.metadata.from)}</span>
                <time datetime="${message.metadata.timestamp}" class="timestamp">
                    ${time}, ${duration}s
                </time>
                ${message.metadata.authenticated ? 
                    '<span class="auth-indicator verified" aria-label="Authenticated transmission">🔒</span>' : 
                    ''}
            </header>
            
            <div class="audio-controls">
                <button class="play-btn ${isPlaying ? 'playing' : ''}" 
                        onclick="window.radioController.audioManager.playMessage('${message.id}')"
                        aria-label="Play audio message from ${message.metadata.from}, ${time}, ${duration} seconds duration"
                        ${isPlaying ? 'disabled' : ''}>
                    ${isPlaying ? '⏸️ Playing' : '▶️ Play Audio'}
                </button>
                
                <div class="audio-metadata" aria-label="Audio details">
                    Duration: ${duration}s | Quality: ${message.metadata.quality}
                    ${message.metadata.authenticated ? ' | Authenticated' : ''}
                </div>
            </div>
            
            <div class="transcript-placeholder" role="region" aria-label="Audio transcript">
                <p class="transcript-text">
                    [Transcript will be available in Phase 3]
                </p>
            </div>
        `;
        
        return messageEl;
    }
    
    /**
     * Utility: Escape HTML
     */
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
    
    /**
     * Future: Process audio blob (Phase 2)
     */
    async processAudioBlob(audioBlob, messageId) {
        // Phase 2: Convert blob to URL, extract waveform data
        console.log('Audio blob processing will be implemented in Phase 2');
        return null;
    }
    
    /**
     * Future: Transcribe audio (Phase 3)
     */
    async transcribeAudio(messageId) {
        // Phase 3: Implement transcription
        console.log('Audio transcription will be implemented in Phase 3');
        return null;
    }
}

// Make AudioManager available globally
window.AudioManager = AudioManager;
