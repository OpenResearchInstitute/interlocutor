/**
 * Accessibility Announcement System for Radio Interface
 * Provides screen reader announcements for dynamic content changes
 */

class AccessibilityAnnouncer {
    constructor() {
        this.politeRegion = document.getElementById('sr-announcements');
        this.assertiveRegion = document.getElementById('sr-status');
        
        // Fallback if regions don't exist
        if (!this.politeRegion) {
            this.politeRegion = this.createAnnouncementRegion('sr-announcements', 'polite');
        }
        if (!this.assertiveRegion) {
            this.assertiveRegion = this.createAnnouncementRegion('sr-status', 'assertive');
        }
        
        // Track announcement history to avoid spam
        this.lastAnnouncement = '';
        this.lastAnnouncementTime = 0;
        this.debounceDelay = 1000; // 1 second minimum between identical announcements
    }
    
    /**
     * Create announcement region if it doesn't exist
     */
    createAnnouncementRegion(id, liveType) {
        const region = document.createElement('div');
        region.id = id;
        region.setAttribute('aria-live', liveType);
        region.setAttribute('aria-atomic', 'true');
        region.className = 'sr-only';
        
        // Add screen reader only CSS if not already present
        if (!document.querySelector('.sr-only')) {
            const style = document.createElement('style');
            style.textContent = `
                .sr-only {
                    position: absolute !important;
                    width: 1px !important;
                    height: 1px !important;
                    padding: 0 !important;
                    margin: -1px !important;
                    overflow: hidden !important;
                    clip: rect(0, 0, 0, 0) !important;
                    white-space: nowrap !important;
                    border: 0 !important;
                }
            `;
            document.head.appendChild(style);
        }
        
        document.body.appendChild(region);
        return region;
    }
    
    /**
     * Announce message politely (doesn't interrupt current speech)
     * Use for: New messages, status updates, non-critical information
     */
    announcePolite(message) {
        if (this.shouldAnnounce(message)) {
            this.clearAndAnnounce(this.politeRegion, message);
            this.updateAnnouncementHistory(message);
        }
    }
    
    /**
     * Announce message assertively (interrupts current speech)
     * Use for: Errors, connection changes, critical alerts
     */
    announceAssertive(message) {
        if (this.shouldAnnounce(message)) {
            this.clearAndAnnounce(this.assertiveRegion, message);
            this.updateAnnouncementHistory(message);
        }
    }
    
    /**
     * Clear region and announce new message
     * This technique ensures screen readers notice the content change
     */
    clearAndAnnounce(region, message) {
        region.textContent = '';
        // Small delay to ensure screen readers notice the change
        setTimeout(() => {
            region.textContent = message;
        }, 100);
    }
    
    /**
     * Check if we should announce (avoid spam)
     */
    shouldAnnounce(message) {
        const now = Date.now();
        const isDuplicate = this.lastAnnouncement === message && 
                           (now - this.lastAnnouncementTime) < this.debounceDelay;
        return !isDuplicate;
    }
    
    /**
     * Update announcement tracking
     */
    updateAnnouncementHistory(message) {
        this.lastAnnouncement = message;
        this.lastAnnouncementTime = Date.now();
    }
    
    /**
     * Announce new message received
     */
    announceNewMessage(from, message, isVoice = false) {
        const messageType = isVoice ? 'voice message' : 'text message';
        const announcement = `New ${messageType} from ${from}: ${message}`;
        this.announcePolite(announcement);
    }
    
    /**
     * Announce message sent
     */
    announceMessageSent(message, isVoice = false) {
        const messageType = isVoice ? 'voice message' : 'text message';
        const announcement = `${messageType} sent: ${message}`;
        this.announcePolite(announcement);
    }
    
    /**
     * Announce connection status changes
     */
    announceConnectionStatus(status, details = '') {
        let announcement;
        switch (status.toLowerCase()) {
            case 'connected':
                announcement = `Connected to radio system${details ? ': ' + details : ''}`;
                break;
            case 'disconnected':
                announcement = `Disconnected from radio system${details ? ': ' + details : ''}`;
                break;
            case 'connecting':
                announcement = 'Connecting to radio system';
                break;
            case 'error':
                announcement = `Connection error${details ? ': ' + details : ''}`;
                break;
            default:
                announcement = `Connection status: ${status}${details ? ': ' + details : ''}`;
        }
        this.announceAssertive(announcement);
    }
    
    /**
     * Announce PTT (Push-to-Talk) status
     */
    announcePTTStatus(isTransmitting) {
        const announcement = isTransmitting ? 
            'Transmitting - push to talk active' : 
            'Transmission ended';
        this.announceAssertive(announcement);
    }
    
    /**
     * Announce form errors
     */
    announceFormError(fieldName, errorMessage) {
        const announcement = `Error in ${fieldName}: ${errorMessage}`;
        this.announceAssertive(announcement);
    }
    
    /**
     * Announce successful actions
     */
    announceSuccess(action) {
        const announcement = `Success: ${action}`;
        this.announcePolite(announcement);
    }
    
    /**
     * Announce system log messages (with filtering)
     */
    announceLogMessage(level, message) {
        // Only announce important log messages to avoid spam
        if (level === 'ERROR' || level === 'WARNING') {
            const announcement = `System ${level.toLowerCase()}: ${message}`;
            this.announceAssertive(announcement);
        }
    }
    
    /**
     * Announce tab changes
     */
    announceTabChange(tabName) {
        const announcement = `Switched to ${tabName} tab`;
        this.announcePolite(announcement);
    }
    
    /**
     * Announce configuration changes
     */
    announceConfigChange(setting, newValue) {
        const announcement = `${setting} changed to ${newValue}`;
        this.announcePolite(announcement);
    }
}

// Initialize the announcement system
// Wait for DOM to be ready
let accessibilityAnnouncer;

document.addEventListener('DOMContentLoaded', function() {
    accessibilityAnnouncer = new AccessibilityAnnouncer();
    console.log('🔊 AccessibilityAnnouncer initialized');
});



// Example integration points for your existing code:

/**
 * Integration Examples - Add these to your existing JavaScript files:
 */


// Export for use in other modules if needed
if (typeof module !== 'undefined' && module.exports) {
    module.exports = AccessibilityAnnouncer;
}

// Make available globally
window.AccessibilityAnnouncer = AccessibilityAnnouncer;
window.accessibilityAnnouncer = accessibilityAnnouncer;
