/**
 * Radio Controller - Main application controller for Opulent Voice GUI
 * Coordinates between WebSocket communication, UI updates, and user interactions
 */

class RadioController {
    constructor() {
        this.websocketClient = null;
        this.audioManager = null;
        this.accessibilityManager = null;
        
        // Application state
        this.isConnected = false;
        this.isPTTActive = false;
        this.currentConfig = {};
        this.systemStatus = {};
        this.messageHistory = [];
        
        // UI elements (will be populated in initialize)
        this.elements = {};
        
        // Settings
        this.debugMode = 'normal';
        this.autoScrollMessages = true;
        
        console.log('RadioController initialized');
    }
    
    /**
     * Initialize the application
     */
    async initialize() {
        console.log('Initializing Radio Controller...');
        
        try {
            // Cache DOM elements
            this.cacheElements();
            
            // Initialize components
            await this.initializeComponents();
            
            // Set up event listeners
            this.setupEventListeners();
            
            // Initialize WebSocket connection
            await this.connectToRadioSystem();
            
            console.log('Radio Controller initialization complete');
            
        } catch (error) {
            console.error('Failed to initialize Radio Controller:', error);
            this.showError('Failed to initialize application: ' + error.message);
        }
    }
    
    /**
     * Cache frequently used DOM elements
     */
    cacheElements() {
        this.elements = {
            // Connection status
            connectionStatus: document.getElementById('connection-status'),
            connectionIndicator: document.querySelector('.status-indicator'),
            connectionText: document.querySelector('.status-text'),
            
            // Controls
            pttBtn: document.getElementById('ptt-btn'),
            connectBtn: document.getElementById('connect-btn'),
            disconnectBtn: document.getElementById('disconnect-btn'),
            
            // Network settings
            targetIpInput: document.getElementById('target-ip'),
            targetPortInput: document.getElementById('target-port'),
            
            // Chat
            messageHistory: document.getElementById('message-history'),
            messageInput: document.getElementById('message-input'),
            messageForm: document.getElementById('message-form'),
            messageStatus: document.getElementById('message-status'),
            sendBtn: document.querySelector('.send-btn'),
            
            // Status display
            stationId: document.getElementById('station-id'),
            messagesSent: document.getElementById('messages-sent'),
            messagesReceived: document.getElementById('messages-received'),
            audioMessagesCount: document.getElementById('audio-messages-count'),
            
            // System log
            systemLog: document.getElementById('system-log'),
            logLevel: document.getElementById('log-level'),
            clearLogBtn: document.getElementById('clear-log-btn'),
            
            // Settings
            settingsBtn: document.getElementById('settings-btn'),
            settingsPanel: document.getElementById('settings-panel'),
            closeSettingsBtn: document.getElementById('close-settings-btn'),
            debugModeRadios: document.querySelectorAll('input[name="debug-mode"]'),
            audioSetupBtn: document.getElementById('audio-setup-btn'),
            
            // Accessibility
            accessibilityMenuBtn: document.getElementById('accessibility-menu-btn'),
            accessibilityMenu: document.getElementById('accessibility-menu'),
            highContrastToggle: document.getElementById('high-contrast-toggle'),
            reduceMotionToggle: document.getElementById('reduce-motion-toggle'),
            screenReaderMode: document.getElementById('screen-reader-mode'),
            
            // Screen reader announcements
            srAnnouncements: document.getElementById('sr-announcements'),
            srStatus: document.getElementById('sr-status'),
            
            // Loading overlay
            loadingOverlay: document.getElementById('loading-overlay'),
            loadingMessage: document.getElementById('loading-message')
        };
        
        console.log('DOM elements cached');
    }
    
    /**
     * Initialize application components
     */
    async initializeComponents() {
        // Initialize WebSocket client
        this.websocketClient = new WebSocketClient();
        this.websocketClient.onMessage = this.handleWebSocketMessage.bind(this);
        this.websocketClient.onConnect = this.handleWebSocketConnect.bind(this);
        this.websocketClient.onDisconnect = this.handleWebSocketDisconnect.bind(this);
        this.websocketClient.onError = this.handleWebSocketError.bind(this);
        
        // Initialize audio manager (for future audio replay)
        this.audioManager = new AudioManager();
        
        // Initialize accessibility manager
        this.accessibilityManager = new AccessibilityManager();
        this.accessibilityManager.initialize();
        
        console.log('Components initialized');
    }
    
    /**
     * Set up event listeners for UI interactions
     */
    setupEventListeners() {
        // PTT button
        this.elements.pttBtn.addEventListener('mousedown', this.handlePTTPress.bind(this));
        this.elements.pttBtn.addEventListener('mouseup', this.handlePTTRelease.bind(this));
        this.elements.pttBtn.addEventListener('mouseleave', this.handlePTTRelease.bind(this));
        
        // Connection controls
        this.elements.connectBtn.addEventListener('click', this.handleConnect.bind(this));
        this.elements.disconnectBtn.addEventListener('click', this.handleDisconnect.bind(this));
        
        // Network settings
        this.elements.targetIpInput.addEventListener('change', this.handleNetworkSettingChange.bind(this));
        this.elements.targetPortInput.addEventListener('change', this.handleNetworkSettingChange.bind(this));
        
        // Message form
        this.elements.messageForm.addEventListener('submit', this.handleMessageSubmit.bind(this));
        this.elements.messageInput.addEventListener('input', this.handleMessageInput.bind(this));
        
        // Settings panel
        this.elements.settingsBtn.addEventListener('click', this.toggleSettingsPanel.bind(this));
        this.elements.closeSettingsBtn.addEventListener('click', this.closeSettingsPanel.bind(this));
        
        // Debug mode radios
        this.elements.debugModeRadios.forEach(radio => {
            radio.addEventListener('change', this.handleDebugModeChange.bind(this));
        });
        
        // Audio setup
        this.elements.audioSetupBtn.addEventListener('click', this.handleAudioSetup.bind(this));
        
        // System log controls
        this.elements.clearLogBtn.addEventListener('click', this.clearSystemLog.bind(this));
        this.elements.logLevel.addEventListener('change', this.handleLogLevelChange.bind(this));
        
        // Accessibility menu
        this.elements.accessibilityMenuBtn.addEventListener('click', this.toggleAccessibilityMenu.bind(this));
        this.elements.highContrastToggle.addEventListener('change', this.handleAccessibilityToggle.bind(this));
        this.elements.reduceMotionToggle.addEventListener('change', this.handleAccessibilityToggle.bind(this));
        this.elements.screenReaderMode.addEventListener('change', this.handleAccessibilityToggle.bind(this));
        
        // Keyboard shortcuts
        document.addEventListener('keydown', this.handleKeyboardShortcuts.bind(this));
        
        // Window events
        window.addEventListener('beforeunload', this.handleWindowUnload.bind(this));
        
        console.log('Event listeners set up');
    }
    
    /**
     * Connect to the radio system via WebSocket
     */
    async connectToRadioSystem() {
        this.showLoading('Connecting to radio system...');
        
        try {
            const wsUrl = `ws://${window.location.hostname}:${window.location.port || 8000}/ws`;
            await this.websocketClient.connect(wsUrl);
        } catch (error) {
            console.error('Failed to connect to radio system:', error);
            this.hideLoading();
            this.showError('Failed to connect to radio system. Please check that the server is running.');
        }
    }
    
    /**
     * WebSocket message handler
     */
    handleWebSocketMessage(message) {
        console.log('WebSocket message received:', message);
        
        switch (message.type) {
            case 'initial_status':
                this.handleInitialStatus(message.data);
                break;
                
            case 'status_update':
                this.handleStatusUpdate(message.data);
                break;
                
            case 'message_received':
                this.handleMessageReceived(message.data);
                break;
                
            case 'message_sent':
                this.handleMessageSent(message.data);
                break;
                
            case 'ptt_state_changed':
                this.handlePTTStateChanged(message.data);
                break;
                
            case 'audio_message_available':
                this.handleAudioMessageAvailable(message.data);
                break;
                
            case 'config_updated':
                this.handleConfigUpdated(message.data);
                break;
                
            case 'debug_mode_changed':
                this.handleDebugModeChanged(message.data);
                break;
                
            case 'error':
                this.showError(message.message || 'Unknown error occurred');
                break;
                
            default:
                console.warn('Unknown message type:', message.type);
        }
    }
    
    /**
     * Handle WebSocket connection established
     */
    handleWebSocketConnect() {
        console.log('WebSocket connected');
        this.isConnected = true;
        this.updateConnectionStatus('connected', 'Connected to radio system');
        this.hideLoading();
        this.enableControls();
        this.announceToScreenReader('Connected to radio system');
    }
    
    /**
     * Handle WebSocket disconnection
     */
    handleWebSocketDisconnect() {
        console.log('WebSocket disconnected');
        this.isConnected = false;
        this.updateConnectionStatus('disconnected', 'Disconnected from radio system');
        this.disableControls();
        this.announceToScreenReader('Disconnected from radio system');
    }
    
    /**
     * Handle WebSocket error
     */
    handleWebSocketError(error) {
        console.error('WebSocket error:', error);
        this.showError('Connection error: ' + error.message);
        this.updateConnectionStatus('error', 'Connection error');
    }
    
    /**
     * Handle initial status from server
     */
    handleInitialStatus(status) {
        console.log('Initial status received:', status);
        this.systemStatus = status;
        this.updateUI();
        this.logMessage('info', 'Connected to radio system');
        
        // Set debug mode from server
        if (status.debug_mode) {
            this.setDebugMode(status.debug_mode);
        }
    }
    
    /**
     * Handle status updates from server
     */
    handleStatusUpdate(status) {
        Object.assign(this.systemStatus, status);
        this.updateUI();
    }
    
    /**
     * Handle received message
     */
    handleMessageReceived(messageData) {
        const message = {
            type: messageData.type || 'text',
            direction: 'incoming',
            content: messageData.content || messageData.message || '',
            from: messageData.from || 'UNKNOWN',
            timestamp: messageData.timestamp || new Date().toISOString(),
            metadata: messageData.metadata || {}
        };
        
        this.addMessageToHistory(message);
        this.announceToScreenReader(`Message from ${message.from}: ${message.content}`);
        this.logMessage('info', `Message received from ${message.from}`);
    }
    
    /**
     * Handle message sent confirmation
     */
    handleMessageSent(messageData) {
        const message = {
            type: 'text',
            direction: 'outgoing',
            content: messageData.message,
            from: this.systemStatus.station_id || 'LOCAL',
            timestamp: messageData.timestamp,
            metadata: {}
        };
        
        this.addMessageToHistory(message);
        this.elements.messageStatus.textContent = 'Message sent';
        this.elements.messageStatus.className = 'input-status success';
        
        setTimeout(() => {
            this.elements.messageStatus.textContent = '';
            this.elements.messageStatus.className = 'input-status';
        }, 2000);
    }
    
    /**
     * Handle PTT state change from server
     */
    handlePTTStateChanged(data) {
        this.isPTTActive = data.active;
        this.updatePTTButton();
        
        const status = data.active ? 'PTT Active - Transmitting' : 'PTT Released';
        this.announceToScreenReader(status);
        this.logMessage('info', status);
    }
    
    /**
     * Handle new audio message available
     */
    handleAudioMessageAvailable(data) {
        console.log('Audio message available:', data);
        this.audioManager.addAudioMessage(data);
        this.updateAudioMessageCount();
        this.announceToScreenReader(`New audio message from ${data.metadata.from || 'unknown station'}`);
    }
    
    /**
     * Handle configuration update
     */
    handleConfigUpdated(data) {
        Object.assign(this.currentConfig, data);
        this.logMessage('info', 'Configuration updated');
    }
    
    /**
     * Handle debug mode change from server
     */
    handleDebugModeChanged(data) {
        this.setDebugMode(data.mode);
    }
    
    /**
     * Handle PTT button press
     */
    handlePTTPress(event) {
        if (!this.isConnected) return;
        
        event.preventDefault();
        this.sendCommand('ptt_press', {});
        this.elements.pttBtn.setAttribute('aria-pressed', 'true');
        this.announceToScreenReader('PTT pressed - transmitting');
    }
    
    /**
     * Handle PTT button release
     */
    handlePTTRelease(event) {
        if (!this.isConnected) return;
        
        event.preventDefault();
        this.sendCommand('ptt_release', {});
        this.elements.pttBtn.setAttribute('aria-pressed', 'false');
        this.announceToScreenReader('PTT released');
    }
    
    /**
     * Handle connect button click
     */
    handleConnect() {
        if (this.isConnected) return;
        this.connectToRadioSystem();
    }
    
    /**
     * Handle disconnect button click
     */
    handleDisconnect() {
        if (!this.isConnected) return;
        this.websocketClient.disconnect();
    }
    
    /**
     * Handle network setting changes
     */
    handleNetworkSettingChange() {
        const ip = this.elements.targetIpInput.value.trim();
        const port = parseInt(this.elements.targetPortInput.value);
        
        if (this.validateNetworkSettings(ip, port)) {
            this.sendCommand('update_config', {
                target_ip: ip,
                target_port: port
            });
        }
    }
    
    /**
     * Handle message form submission
     */
    handleMessageSubmit(event) {
        event.preventDefault();
        
        const message = this.elements.messageInput.value.trim();
        if (!message || !this.isConnected) return;
        
        this.sendCommand('send_text_message', { message: message });
        this.elements.messageInput.value = '';
        this.elements.messageStatus.textContent = 'Sending...';
        this.elements.messageStatus.className = 'input-status info';
    }
    
    /**
     * Handle message input changes
     */
    handleMessageInput() {
        // Could add typing indicators or validation here
    }
    
    /**
     * Handle debug mode change
     */
    handleDebugModeChange(event) {
        if (event.target.checked) {
            this.sendCommand('set_debug_mode', { mode: event.target.value });
        }
    }
    
    /**
     * Handle audio setup
     */
    handleAudioSetup() {
        // This will be expanded in Phase 2
        this.showInfo('Audio setup will be available in the next phase');
    }
    
    /**
     * Handle keyboard shortcuts
     */
    handleKeyboardShortcuts(event) {
        // PTT with spacebar (when not in input field)
        if (event.code === 'Space' && event.target.tagName !== 'INPUT' && event.target.tagName !== 'TEXTAREA') {
            event.preventDefault();
            if (event.type === 'keydown' && !event.repeat) {
                this.handlePTTPress(event);
            } else if (event.type === 'keyup') {
                this.handlePTTRelease(event);
            }
        }
        
        // Settings panel with Ctrl+S
        if (event.ctrlKey && event.key === 's') {
            event.preventDefault();
            this.toggleSettingsPanel();
        }
        
        // Escape key
        if (event.key === 'Escape') {
            this.closeSettingsPanel();
            this.closeAccessibilityMenu();
        }
    }
    
    /**
     * Handle window unload
     */
    handleWindowUnload() {
        if (this.websocketClient) {
            this.websocketClient.disconnect();
        }
    }
    
    /**
     * Send command to server
     */
    sendCommand(action, data) {
        if (!this.websocketClient || !this.isConnected) {
            console.warn('Cannot send command - not connected');
            return;
        }
        
        this.websocketClient.send({
            action: action,
            data: data
        });
    }
    
    /**
     * Update the main UI based on current state
     */
    updateUI() {
        // Update station ID
        if (this.systemStatus.station_id) {
            this.elements.stationId.textContent = this.systemStatus.station_id;
        }
        
        // Update statistics
        if (this.systemStatus.stats) {
            const stats = this.systemStatus.stats;
            this.elements.messagesSent.textContent = stats.messages_sent || 0;
            this.elements.messagesReceived.textContent = stats.messages_received || 0;
            this.elements.audioMessagesCount.textContent = stats.audio_messages_stored || 0;
        }
        
        // Update network settings
        if (this.systemStatus.config) {
            const config = this.systemStatus.config;
            if (config.target_ip) {
                this.elements.targetIpInput.value = config.target_ip;
            }
            if (config.target_port) {
                this.elements.targetPortInput.value = config.target_port;
            }
        }
        
        // Update PTT button
        this.updatePTTButton();
    }
    
    /**
     * Update PTT button state
     */
    updatePTTButton() {
        const btn = this.elements.pttBtn;
        const status = this.elements.pttStatus || document.getElementById('ptt-status');
        
        if (this.isPTTActive) {
            btn.classList.add('active');
            btn.setAttribute('aria-pressed', 'true');
            btn.setAttribute('aria-label', 'Push to Talk - Currently Transmitting');
            if (status) status.textContent = 'Transmitting';
        } else {
            btn.classList.remove('active');
            btn.setAttribute('aria-pressed', 'false');
            btn.setAttribute('aria-label', 'Push to Talk - Currently Released');
            if (status) status.textContent = this.isConnected ? 'Ready' : 'Disconnected';
        }
    }
    
    /**
     * Update connection status display
     */
    updateConnectionStatus(status, text) {
        this.elements.connectionIndicator.className = `status-indicator ${status}`;
        this.elements.connectionText.textContent = text;
        
        // Update aria-label for screen readers
        this.elements.connectionStatus.setAttribute('aria-label', `Connection status: ${text}`);
    }
    
    /**
     * Add message to chat history
     */
    addMessageToHistory(message) {
        this.messageHistory.push(message);
        
        // Create message element
        const messageEl = this.createMessageElement(message);
        
        // Remove welcome message if it exists
        const welcomeMsg = this.elements.messageHistory.querySelector('.welcome-message');
        if (welcomeMsg) {
            welcomeMsg.remove();
        }
        
        // Add new message
        this.elements.messageHistory.appendChild(messageEl);
        
        // Auto-scroll if enabled
        if (this.autoScrollMessages) {
            this.elements.messageHistory.scrollTop = this.elements.messageHistory.scrollHeight;
        }
        
        // Limit message history
        const maxMessages = 100;
        while (this.elements.messageHistory.children.length > maxMessages) {
            this.elements.messageHistory.removeChild(this.elements.messageHistory.firstChild);
        }
    }
    
    /**
     * Create message element for display
     */
    createMessageElement(message) {
        const messageEl = document.createElement('div');
        messageEl.className = `message ${message.direction}`;
        messageEl.setAttribute('role', 'article');
        
        const time = new Date(message.timestamp).toLocaleTimeString();
        
        messageEl.innerHTML = `
            <div class="message-header">
                <span class="message-from">${this.escapeHtml(message.from)}</span>
                <time class="message-time" datetime="${message.timestamp}">${time}</time>
            </div>
            <div class="message-content">${this.escapeHtml(message.content)}</div>
        `;
        
        return messageEl;
    }
    
    /**
     * Utility functions
     */
    
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
    
    validateNetworkSettings(ip, port) {
        // Basic IP validation
        const ipRegex = /^(\d{1,3}\.){3}\d{1,3}$/;
        if (!ipRegex.test(ip)) {
            this.showError('Invalid IP address format');
            return false;
        }
        
        // Port validation
        if (isNaN(port) || port < 1 || port > 65535) {
            this.showError('Port must be between 1 and 65535');
            return false;
        }
        
        return true;
    }
    
    setDebugMode(mode) {
        this.debugMode = mode;
        
        // Update radio buttons
        this.elements.debugModeRadios.forEach(radio => {
            radio.checked = radio.value === mode;
        });
        
        this.logMessage('info', `Debug mode set to: ${mode}`);
    }
    
    enableControls() {
        this.elements.pttBtn.disabled = false;
        this.elements.disconnectBtn.disabled = false;
        this.elements.messageInput.disabled = false;
        this.elements.sendBtn.disabled = false;
        this.elements.connectBtn.disabled = true;
    }
    
    disableControls() {
        this.elements.pttBtn.disabled = true;
        this.elements.connectBtn.disabled = false;
        this.elements.disconnectBtn.disabled = true;
        this.elements.messageInput.disabled = true;
        this.elements.sendBtn.disabled = true;
    }
    
    showLoading(message) {
        this.elements.loadingMessage.textContent = message;
        this.elements.loadingOverlay.hidden = false;
    }
    
    hideLoading() {
        this.elements.loadingOverlay.hidden = true;
    }
    
    showError(message) {
        console.error(message);
        this.logMessage('error', message);
        this.announceToScreenReader(`Error: ${message}`);
        // Could show a toast notification here
    }
    
    showInfo(message) {
        console.info(message);
        this.logMessage('info', message);
        this.announceToScreenReader(message);
    }
    
    logMessage(level, message) {
        const timestamp = new Date().toLocaleTimeString();
        const logEntry = document.createElement('div');
        logEntry.className = `log-entry ${level}`;
        logEntry.innerHTML = `
            <span class="log-time">${timestamp}</span>
            <span class="log-level">${level.toUpperCase()}</span>
            <span class="log-message">${this.escapeHtml(message)}</span>
        `;
        
        this.elements.systemLog.appendChild(logEntry);
        
        // Auto-scroll log
        this.elements.systemLog.scrollTop = this.elements.systemLog.scrollHeight;
        
        // Limit log entries
        while (this.elements.systemLog.children.length > 200) {
            this.elements.systemLog.removeChild(this.elements.systemLog.firstChild);
        }
    }
    
    clearSystemLog() {
        this.elements.systemLog.innerHTML = '';
        this.announceToScreenReader('System log cleared');
    }
    
    handleLogLevelChange() {
        const level = this.elements.logLevel.value;
        // Filter log entries by level (implementation depends on needs)
        console.log('Log level changed to:', level);
    }
    
    announceToScreenReader(message) {
        // Use polite announcements for most messages
        this.elements.srAnnouncements.textContent = message;
        
        // Clear after a short delay to allow re-announcement of same message
        setTimeout(() => {
            this.elements.srAnnouncements.textContent = '';
        }, 1000);
    }
    
    announceUrgentToScreenReader(message) {
        // Use assertive announcements for urgent messages
        this.elements.srStatus.textContent = message;
        
        setTimeout(() => {
            this.elements.srStatus.textContent = '';
        }, 1000);
    }
    
    toggleSettingsPanel() {
        const panel = this.elements.settingsPanel;
        const btn = this.elements.settingsBtn;
        
        if (panel.hidden) {
            panel.hidden = false;
            btn.setAttribute('aria-expanded', 'true');
            // Focus management for accessibility
            this.elements.closeSettingsBtn.focus();
        } else {
            this.closeSettingsPanel();
        }
    }
    
    closeSettingsPanel() {
        const panel = this.elements.settingsPanel;
        const btn = this.elements.settingsBtn;
        
        panel.hidden = true;
        btn.setAttribute('aria-expanded', 'false');
        btn.focus(); // Return focus to trigger button
    }
    
    toggleAccessibilityMenu() {
        const menu = this.elements.accessibilityMenu;
        const btn = this.elements.accessibilityMenuBtn;
        
        if (menu.hidden) {
            menu.hidden = false;
            btn.setAttribute('aria-expanded', 'true');
        } else {
            this.closeAccessibilityMenu();
        }
    }
    
    closeAccessibilityMenu() {
        const menu = this.elements.accessibilityMenu;
        const btn = this.elements.accessibilityMenuBtn;
        
        menu.hidden = true;
        btn.setAttribute('aria-expanded', 'false');
    }
    
    handleAccessibilityToggle(event) {
        const setting = event.target.id;
        const enabled = event.target.checked;
        
        // Apply accessibility settings
        this.accessibilityManager.setSetting(setting, enabled);
        
        this.logMessage('info', `Accessibility setting ${setting}: ${enabled ? 'enabled' : 'disabled'}`);
    }
    
    updateAudioMessageCount() {
        const count = this.audioManager.getMessageCount();
        this.elements.audioMessagesCount.textContent = count;
    }
}

// Make RadioController available globally
window.RadioController = RadioController;