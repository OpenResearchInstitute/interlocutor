/**
 * WebSocket Client for Opulent Voice Radio Interface
 * Handles real-time communication with the radio system backend
 */

class WebSocketClient {
    constructor() {
        this.socket = null;
        this.isConnected = false;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.reconnectDelay = 1000; // Start with 1 second
        this.maxReconnectDelay = 30000; // Max 30 seconds
        this.reconnectTimer = null;
        this.pingTimer = null;
        this.lastPingTime = 0;
        
        // Event handlers (to be set by parent)
        this.onConnect = null;
        this.onDisconnect = null;
        this.onMessage = null;
        this.onError = null;
        
        console.log('WebSocketClient initialized');
    }
    
    /**
     * Connect to WebSocket server
     */
    async connect(url) {
        if (this.socket && this.socket.readyState === WebSocket.OPEN) {
            console.log('WebSocket already connected');
            return;
        }
        
        console.log('Connecting to WebSocket:', url);
        
        try {
            this.socket = new WebSocket(url);
            this.setupEventHandlers();
            
            // Return a promise that resolves when connected
            return new Promise((resolve, reject) => {
                const timeout = setTimeout(() => {
                    reject(new Error('Connection timeout'));
                }, 10000);
                
                this.socket.addEventListener('open', () => {
                    clearTimeout(timeout);
                    resolve();
                });
                
                this.socket.addEventListener('error', (error) => {
                    clearTimeout(timeout);
                    reject(error);
                });
            });
            
        } catch (error) {
            console.error('Failed to create WebSocket connection:', error);
            throw error;
        }
    }
    
    /**
     * Disconnect from WebSocket server
     */
    disconnect() {
        console.log('Disconnecting WebSocket');
        
        this.clearReconnectTimer();
        this.clearPingTimer();
        
        if (this.socket) {
            this.socket.close(1000, 'User initiated disconnect');
        }
    }
    
    /**
     * Send message to server
     */
    send(message) {
        if (!this.isConnected || !this.socket) {
            console.warn('Cannot send message - WebSocket not connected');
            return false;
        }
        
        try {
            const messageStr = JSON.stringify(message);
            this.socket.send(messageStr);
            console.log('Sent message:', message);
            return true;
        } catch (error) {
            console.error('Failed to send message:', error);
            return false;
        }
    }
    
    /**
     * Setup WebSocket event handlers
     */
    setupEventHandlers() {
        this.socket.addEventListener('open', this.handleOpen.bind(this));
        this.socket.addEventListener('close', this.handleClose.bind(this));
        this.socket.addEventListener('error', this.handleError.bind(this));
        this.socket.addEventListener('message', this.handleMessage.bind(this));
    }
    
    /**
     * Handle WebSocket open event
     */
    handleOpen(event) {
        console.log('WebSocket connected');
        
        this.isConnected = true;
        this.reconnectAttempts = 0;
        this.reconnectDelay = 1000; // Reset delay
        
        this.clearReconnectTimer();
        this.startPingTimer();
        
        if (this.onConnect) {
            this.onConnect(event);
        }
    }
    
    /**
     * Handle WebSocket close event
     */
    handleClose(event) {
        console.log('WebSocket closed:', event.code, event.reason);
        
        this.isConnected = false;
        this.clearPingTimer();
        
        if (this.onDisconnect) {
            this.onDisconnect(event);
        }
        
        // Attempt reconnection if not a clean close
        if (event.code !== 1000 && this.reconnectAttempts < this.maxReconnectAttempts) {
            this.scheduleReconnect();
        }
    }
    
    /**
     * Handle WebSocket error event
     */
    handleError(event) {
        console.error('WebSocket error:', event);
        
        if (this.onError) {
            this.onError(new Error('WebSocket connection error'));
        }
    }
    
    /**
     * Handle incoming WebSocket message
     */
    handleMessage(event) {
        try {
            const message = JSON.parse(event.data);
            console.log('Received message:', message);
            
            // Handle internal message types
            if (message.type === 'ping') {
                this.handlePing();
                return;
            }
            
            if (message.type === 'pong') {
                this.handlePong();
                return;
            }
            
            // Pass other messages to parent handler
            if (this.onMessage) {
                this.onMessage(message);
            }
            
        } catch (error) {
            console.error('Failed to parse WebSocket message:', error);
            console.error('Raw message:', event.data);
        }
    }
    
    /**
     * Handle ping from server
     */
    handlePing() {
        // Respond with pong
        this.send({ type: 'pong', timestamp: Date.now() });
    }
    
    /**
     * Handle pong response from server
     */
    handlePong() {
        const now = Date.now();
        const latency = now - this.lastPingTime;
        console.log(`WebSocket latency: ${latency}ms`);
    }
    
    /**
     * Schedule reconnection attempt
     */
    scheduleReconnect() {
        if (this.reconnectTimer) {
            return; // Already scheduled
        }
        
        this.reconnectAttempts++;
        const delay = Math.min(this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1), this.maxReconnectDelay);
        
        console.log(`Scheduling reconnect attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts} in ${delay}ms`);
        
        this.reconnectTimer = setTimeout(async () => {
            this.reconnectTimer = null;
            
            try {
                // Try to reconnect to the same URL
                const url = this.socket ? this.socket.url : `ws://${window.location.hostname}:${window.location.port || 8000}/ws`;
                await this.connect(url);
            } catch (error) {
                console.error('Reconnection failed:', error);
                
                if (this.reconnectAttempts < this.maxReconnectAttempts) {
                    this.scheduleReconnect();
                } else {
                    console.error('Max reconnection attempts reached');
                    if (this.onError) {
                        this.onError(new Error('Failed to reconnect after maximum attempts'));
                    }
                }
            }
        }, delay);
    }
    
    /**
     * Clear reconnection timer
     */
    clearReconnectTimer() {
        if (this.reconnectTimer) {
            clearTimeout(this.reconnectTimer);
            this.reconnectTimer = null;
        }
    }
    
    /**
     * Start ping timer to keep connection alive
     */
    startPingTimer() {
        this.clearPingTimer();
        
        this.pingTimer = setInterval(() => {
            if (this.isConnected) {
                this.lastPingTime = Date.now();
                this.send({ type: 'ping', timestamp: this.lastPingTime });
            }
        }, 30000); // Ping every 30 seconds
    }
    
    /**
     * Clear ping timer
     */
    clearPingTimer() {
        if (this.pingTimer) {
            clearInterval(this.pingTimer);
            this.pingTimer = null;
        }
    }
    
    /**
     * Get connection status
     */
    getStatus() {
        return {
            connected: this.isConnected,
            reconnectAttempts: this.reconnectAttempts,
            readyState: this.socket ? this.socket.readyState : WebSocket.CLOSED,
            url: this.socket ? this.socket.url : null
        };
    }
    
    /**
     * Reset reconnection state
     */
    resetReconnection() {
        this.reconnectAttempts = 0;
        this.reconnectDelay = 1000;
        this.clearReconnectTimer();
    }
}

// Make WebSocketClient available globally
window.WebSocketClient = WebSocketClient;