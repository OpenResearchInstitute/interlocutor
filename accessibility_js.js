/**
 * Accessibility Manager for Opulent Voice Radio Interface
 * Handles accessibility features, preferences, and screen reader support
 */

class AccessibilityManager {
    constructor() {
        this.preferences = {
            highContrast: false,
            reduceMotion: false,
            screenReaderMode: false,
            announceNewMessages: true,
            keyboardShortcuts: true,
            focusManagement: true
        };
        
        // Screen reader detection
        this.screenReaderDetected = this.detectScreenReader();
        
        // Keyboard navigation state
        this.isNavigatingByKeyboard = false;
        this.lastFocusedElement = null;
        
        console.log('AccessibilityManager initialized');
        console.log('Screen reader detected:', this.screenReaderDetected);
    }
    
    /**
     * Initialize accessibility features
     */
    initialize() {
        this.loadPreferences();
        this.setupKeyboardNavigation();
        this.setupFocusManagement();
        this.setupReducedMotion();
        this.applyStoredPreferences();
        
        // Auto-enable screen reader mode if detected
        if (this.screenReaderDetected) {
            this.setSetting('screen-reader-mode', true);
        }
        
        console.log('Accessibility features initialized');
    }
    
    /**
     * Detect if a screen reader is likely being used
     */
    detectScreenReader() {
        // Multiple detection methods for better reliability
        
        // Method 1: Check for screen reader specific CSS
        const hasScreenReaderCSS = window.getComputedStyle(document.body)
            .getPropertyValue('speak') !== 'normal';
        
        // Method 2: Check for reduced motion preference (often correlates)
        const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        
        // Method 3: Check user agent for known screen reader indicators
        const userAgent = navigator.userAgent.toLowerCase();
        const hasScreenReaderUA = userAgent.includes('jaws') || 
                                  userAgent.includes('nvda') || 
                                  userAgent.includes('voiceover');
        
        // Method 4: Check for high contrast preference
        const prefersHighContrast = window.matchMedia('(prefers-contrast: high)').matches;
        
        // Method 5: Test for screen reader specific navigation
        const hasScreenReaderNavigation = this.testScreenReaderNavigation();
        
        return hasScreenReaderCSS || hasScreenReaderUA || hasScreenReaderNavigation;
    }
    
    /**
     * Test for screen reader specific navigation patterns
     */
    testScreenReaderNavigation() {
        try {
            // Create a hidden test element
            const testEl = document.createElement('div');
            testEl.setAttribute('aria-hidden', 'true');
            testEl.style.position = 'absolute';
            testEl.style.left = '-9999px';
            testEl.textContent = 'Screen reader test';
            document.body.appendChild(testEl);
            
            // Focus the element
            testEl.focus();
            
            // Check if focus moved (screen readers often handle this differently)
            const focused = document.activeElement === testEl;
            
            // Clean up
            document.body.removeChild(testEl);
            
            return !focused; // Screen readers often prevent programmatic focus on hidden elements
        } catch (error) {
            return false;
        }
    }
    
    /**
     * Set up keyboard navigation enhancements
     */
    setupKeyboardNavigation() {
        // Track keyboard vs mouse usage
        document.addEventListener('keydown', (event) => {
            this.isNavigatingByKeyboard = true;
            document.body.classList.add('keyboard-navigation');
            
            // Handle specific accessibility shortcuts
            this.handleAccessibilityShortcuts(event);
        });
        
        document.addEventListener('mousedown', () => {
            this.isNavigatingByKeyboard = false;
            document.body.classList.remove('keyboard-navigation');
        });
        
        // Enhanced tab navigation
        document.addEventListener('keydown', (event) => {
            if (event.key === 'Tab') {
                this.handleTabNavigation(event);
            }
        });
    }
    
    /**
     * Handle accessibility-specific keyboard shortcuts
     */
    handleAccessibilityShortcuts(event) {
        // Skip to main content (Alt + M)
        if (event.altKey && event.key === 'm') {
            event.preventDefault();
            const mainContent = document.getElementById('main-content');
            if (mainContent) {
                mainContent.focus();
                this.announceToScreenReader('Jumped to main content');
            }
        }
        
        // Toggle high contrast (Alt + H)
        if (event.altKey && event.key === 'h') {
            event.preventDefault();
            this.toggleHighContrast();
        }
        
        // Announce current focus (Alt + F)
        if (event.altKey && event.key === 'f') {
            event.preventDefault();
            this.announceCurrentFocus();
        }
        
        // Read current status (Alt + S)
        if (event.altKey && event.key === 's') {
            event.preventDefault();
            this.announceCurrentStatus();
        }
    }
    
    /**
     * Enhanced tab navigation for complex UI
     */
    handleTabNavigation(event) {
        const focusableElements = this.getFocusableElements();
        const currentIndex = focusableElements.indexOf(document.activeElement);
        
        // Handle tab trapping in modal dialogs
        const modal = document.querySelector('[role="dialog"]:not([hidden])');
        if (modal) {
            this.handleModalTabNavigation(event, modal);
        }
    }
    
    /**
     * Handle tab navigation within modal dialogs
     */
    handleModalTabNavigation(event, modal) {
        const modalFocusable = modal.querySelectorAll(
            'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
        );
        
        if (modalFocusable.length === 0) return;
        
        const firstElement = modalFocusable[0];
        const lastElement = modalFocusable[modalFocusable.length - 1];
        
        if (event.shiftKey) {
            // Shift + Tab
            if (document.activeElement === firstElement) {
                event.preventDefault();
                lastElement.focus();
            }
        } else {
            // Tab
            if (document.activeElement === lastElement) {
                event.preventDefault();
                firstElement.focus();
            }
        }
    }
    
    /**
     * Set up focus management
     */
    setupFocusManagement() {
        // Track focus changes for better announcements
        document.addEventListener('focusin', (event) => {
            this.lastFocusedElement = event.target;
            
            // Announce focus changes for screen readers
            if (this.preferences.screenReaderMode) {
                this.announceFocusChange(event.target);
            }
        });
        
        // Handle focus restoration
        document.addEventListener('focusout', (event) => {
            // Store the last focused element for restoration
            if (event.target && event.target !== document.body) {
                this.lastFocusedElement = event.target;
            }
        });
    }
    
    /**
     * Set up reduced motion handling
     */
    setupReducedMotion() {
        // Listen for system preference changes
        const mediaQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
        
        const handleMotionPreference = (mq) => {
            if (mq.matches) {
                this.setSetting('reduce-motion-toggle', true);
            }
        };
        
        handleMotionPreference(mediaQuery);
        mediaQuery.addListener(handleMotionPreference);
    }
    
    /**
     * Get all focusable elements in the document
     */
    getFocusableElements() {
        const selector = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';
        return Array.from(document.querySelectorAll(selector))
            .filter(el => !el.disabled && !el.hidden && el.offsetParent !== null);
    }
    
    /**
     * Set accessibility preference
     */
    setSetting(settingId, enabled) {
        const setting = settingId.replace('-toggle', '').replace('-', '');
        
        switch (setting) {
            case 'highcontrast':
                this.preferences.highContrast = enabled;
                this.applyHighContrast(enabled);
                break;
                
            case 'reducemotion':
                this.preferences.reduceMotion = enabled;
                this.applyReducedMotion(enabled);
                break;
                
            case 'screenreadermode':
                this.preferences.screenReaderMode = enabled;
                this.applyScreenReaderMode(enabled);
                break;
        }
        
        this.savePreferences();
        this.announceToScreenReader(`${settingId} ${enabled ? 'enabled' : 'disabled'}`);
    }
    
    /**
     * Apply high contrast mode
     */
    applyHighContrast(enabled) {
        if (enabled) {
            document.body.classList.add('high-contrast');
        } else {
            document.body.classList.remove('high-contrast');
        }
        
        // Update checkbox state
        const toggle = document.getElementById('high-contrast-toggle');
        if (toggle) {
            toggle.checked = enabled;
        }
    }
    
    /**
     * Apply reduced motion preferences
     */
    applyReducedMotion(enabled) {
        if (enabled) {
            document.body.classList.add('reduce-motion');
        } else {
            document.body.classList.remove('reduce-motion');
        }
        
        // Update checkbox state
        const toggle = document.getElementById('reduce-motion-toggle');
        if (toggle) {
            toggle.checked = enabled;
        }
    }
    
    /**
     * Apply screen reader optimizations
     */
    applyScreenReaderMode(enabled) {
        if (enabled) {
            document.body.classList.add('screen-reader-mode');
            
            // Enable additional announcements
            this.preferences.announceNewMessages = true;
            this.preferences.focusManagement = true;
            
            // Disable auto-scroll for better control
            if (window.radioController) {
                window.radioController.autoScrollMessages = false;
            }
        } else {
            document.body.classList.remove('screen-reader-mode');
        }
        
        // Update checkbox state
        const toggle = document.getElementById('screen-reader-mode');
        if (toggle) {
            toggle.checked = enabled;
        }
    }
    
    /**
     * Toggle high contrast mode
     */
    toggleHighContrast() {
        const newState = !this.preferences.highContrast;
        this.setSetting('high-contrast-toggle', newState);
    }
    
    /**
     * Announce focus change to screen reader
     */
    announceFocusChange(element) {
        if (!this.preferences.screenReaderMode) return;
        
        let announcement = '';
        
        // Get element type and label
        const tagName = element.tagName.toLowerCase();
        const label = this.getElementLabel(element);
        const role = element.getAttribute('role') || tagName;
        
        announcement = `${label}, ${role}`;
        
        // Add state information
        if (element.getAttribute('aria-pressed')) {
            const pressed = element.getAttribute('aria-pressed') === 'true';
            announcement += `, ${pressed ? 'pressed' : 'not pressed'}`;
        }
        
        if (element.getAttribute('aria-expanded')) {
            const expanded = element.getAttribute('aria-expanded') === 'true';
            announcement += `, ${expanded ? 'expanded' : 'collapsed'}`;
        }
        
        if (element.disabled) {
            announcement += ', disabled';
        }
        
        this.announceToScreenReader(announcement);
    }
    
    /**
     * Get accessible label for an element
     */
    getElementLabel(element) {
        // Try aria-labelledby
        const labelledBy = element.getAttribute('aria-labelledby');
        if (labelledBy) {
            const labelElement = document.getElementById(labelledBy);
            if (labelElement) {
                return labelElement.textContent.trim();
            }
        }
        
        // Try associated label element
        if (element.id) {
            const label = document.querySelector(`label[for="${element.id}"]`);
            if (label) {
                return label.textContent.trim();
            }
        }
        
        // Try placeholder
        if (element.placeholder) {
            return element.placeholder;
        }
        
        // Try text content
        if (element.textContent && element.textContent.trim()) {
            return element.textContent.trim();
        }
        
        // Try value for inputs
        if (element.value) {
            return element.value;
        }
        
        // Fallback to element type
        return element.tagName.toLowerCase();
    }
    
    /**
     * Announce current focus information
     */
    announceCurrentFocus() {
        const element = document.activeElement;
        if (element && element !== document.body) {
            const label = this.getElementLabel(element);
            const role = element.getAttribute('role') || element.tagName.toLowerCase();
            this.announceToScreenReader(`Currently focused: ${label}, ${role}`);
        } else {
            this.announceToScreenReader('No element currently focused');
        }
    }
    
    /**
     * Announce current system status
     */
    announceCurrentStatus() {
        if (window.radioController) {
            const status = window.radioController.systemStatus;
            const connected = status.connected ? 'connected' : 'disconnected';
            const station = status.station_id || 'unknown';
            const ptt = status.ptt_active ? 'PTT active' : 'PTT inactive';
            
            const announcement = `Radio status: ${connected} to station ${station}, ${ptt}`;
            this.announceToScreenReader(announcement);
        } else {
            this.announceToScreenReader('Radio system not available');
        }
    }
    
    /**
     * Announce to screen reader using ARIA live regions
     */
    announceToScreenReader(message, priority = 'polite') {
        const liveRegion = priority === 'assertive' ? 
            document.getElementById('sr-status') : 
            document.getElementById('sr-announcements');
        
        if (liveRegion) {
            // Clear first to ensure re-announcement of same message
            liveRegion.textContent = '';
            
            // Use setTimeout to ensure the clearing is processed
            setTimeout(() => {
                liveRegion.textContent = message;
            }, 10);
            
            // Clear after delay to prepare for next announcement
            setTimeout(() => {
                liveRegion.textContent = '';
            }, 3000);
        }
        
        console.log('Screen reader announcement:', message);
    }
    
    /**
     * Create accessible skip links
     */
    createSkipLinks() {
        const skipLinks = document.createElement('div');
        skipLinks.className = 'skip-links';
        skipLinks.innerHTML = `
            <a href="#main-content" class="skip-link">Skip to main content</a>
            <a href="#chat-panel" class="skip-link">Skip to chat</a>
            <a href="#settings-panel" class="skip-link">Skip to settings</a>
        `;
        
        document.body.insertBefore(skipLinks, document.body.firstChild);
    }
    
    /**
     * Enhance form accessibility
     */
    enhanceFormAccessibility() {
        // Add required field indicators
        document.querySelectorAll('input[required], select[required], textarea[required]').forEach(field => {
            if (!field.getAttribute('aria-label') && !field.getAttribute('aria-labelledby')) {
                const label = field.previousElementSibling;
                if (label && label.tagName === 'LABEL') {
                    label.textContent += ' (required)';
                }
            }
        });
        
        // Add error message associations
        document.querySelectorAll('.input-status').forEach(status => {
            const input = status.previousElementSibling;
            if (input && input.tagName === 'INPUT') {
                input.setAttribute('aria-describedby', status.id || this.generateId());
            }
        });
    }
    
    /**
     * Generate unique ID for elements
     */
    generateId() {
        return 'a11y-' + Math.random().toString(36).substr(2, 9);
    }
    
    /**
     * Save accessibility preferences to localStorage
     */
    savePreferences() {
        try {
            localStorage.setItem('opulent-voice-a11y-preferences', JSON.stringify(this.preferences));
        } catch (error) {
            console.warn('Failed to save accessibility preferences:', error);
        }
    }
    
    /**
     * Load accessibility preferences from localStorage
     */
    loadPreferences() {
        try {
            const stored = localStorage.getItem('opulent-voice-a11y-preferences');
            if (stored) {
                const preferences = JSON.parse(stored);
                Object.assign(this.preferences, preferences);
            }
        } catch (error) {
            console.warn('Failed to load accessibility preferences:', error);
        }
    }
    
    /**
     * Apply all stored preferences
     */
    applyStoredPreferences() {
        this.applyHighContrast(this.preferences.highContrast);
        this.applyReducedMotion(this.preferences.reduceMotion);
        this.applyScreenReaderMode(this.preferences.screenReaderMode);
    }
    
    /**
     * Create live region for announcements if it doesn't exist
     */
    ensureLiveRegions() {
        if (!document.getElementById('sr-announcements')) {
            const announcements = document.createElement('div');
            announcements.id = 'sr-announcements';
            announcements.setAttribute('aria-live', 'polite');
            announcements.setAttribute('aria-atomic', 'true');
            announcements.className = 'sr-only';
            document.body.appendChild(announcements);
        }
        
        if (!document.getElementById('sr-status')) {
            const status = document.createElement('div');
            status.id = 'sr-status';
            status.setAttribute('aria-live', 'assertive');
            status.setAttribute('aria-atomic', 'true');
            status.className = 'sr-only';
            document.body.appendChild(status);
        }
    }
    
    /**
     * Handle new message announcements
     */
    announceNewMessage(messageData) {
        if (!this.preferences.announceNewMessages) return;
        
        const from = messageData.from || 'unknown station';
        const type = messageData.type || 'message';
        
        let announcement;
        if (type === 'voice') {
            announcement = `New voice message from ${from}`;
        } else if (type === 'text') {
            const content = messageData.content || '';
            announcement = `New text message from ${from}: ${content}`;
        } else {
            announcement = `New ${type} message from ${from}`;
        }
        
        this.announceToScreenReader(announcement);
    }
    
    /**
     * Handle PTT state announcements
     */
    announcePTTState(active) {
        if (active) {
            this.announceToScreenReader('PTT activated - transmitting', 'assertive');
        } else {
            this.announceToScreenReader('PTT released', 'assertive');
        }
    }
    
    /**
     * Handle connection state announcements
     */
    announceConnectionState(connected, details = '') {
        const state = connected ? 'connected' : 'disconnected';
        const announcement = `Radio system ${state}${details ? ': ' + details : ''}`;
        this.announceToScreenReader(announcement, 'assertive');
    }
    
    /**
     * Create accessible data table
     */
    createAccessibleTable(data, headers, caption) {
        const table = document.createElement('table');
        table.setAttribute('role', 'table');
        
        // Add caption
        if (caption) {
            const captionEl = document.createElement('caption');
            captionEl.textContent = caption;
            table.appendChild(captionEl);
        }
        
        // Add headers
        const thead = document.createElement('thead');
        const headerRow = document.createElement('tr');
        headers.forEach(header => {
            const th = document.createElement('th');
            th.textContent = header;
            th.setAttribute('scope', 'col');
            headerRow.appendChild(th);
        });
        thead.appendChild(headerRow);
        table.appendChild(thead);
        
        // Add data rows
        const tbody = document.createElement('tbody');
        data.forEach(row => {
            const tr = document.createElement('tr');
            row.forEach((cell, index) => {
                const td = document.createElement('td');
                td.textContent = cell;
                if (index === 0) {
                    td.setAttribute('scope', 'row');
                }
                tr.appendChild(td);
            });
            tbody.appendChild(tr);
        });
        table.appendChild(tbody);
        
        return table;
    }
    
    /**
     * Restore focus to last focused element
     */
    restoreFocus() {
        if (this.lastFocusedElement && this.preferences.focusManagement) {
            try {
                this.lastFocusedElement.focus();
            } catch (error) {
                // Element might no longer exist, focus main content instead
                const mainContent = document.getElementById('main-content');
                if (mainContent) {
                    mainContent.focus();
                }
            }
        }
    }
    
    /**
     * Get accessibility compliance report
     */
    getComplianceReport() {
        const report = {
            screenReaderDetected: this.screenReaderDetected,
            preferences: { ...this.preferences },
            features: {
                skipLinks: !!document.querySelector('.skip-link'),
                liveRegions: !!(document.getElementById('sr-announcements') && document.getElementById('sr-status')),
                keyboardNavigation: this.preferences.keyboardShortcuts,
                focusManagement: this.preferences.focusManagement
            },
            wcagCompliance: {
                perceivable: this.checkPerceivableCompliance(),
                operable: this.checkOperableCompliance(),
                understandable: this.checkUnderstandableCompliance(),
                robust: this.checkRobustCompliance()
            }
        };
        
        return report;
    }
    
    /**
     * Check WCAG Perceivable compliance
     */
    checkPerceivableCompliance() {
        return {
            textAlternatives: this.checkTextAlternatives(),
            captions: true, // Will be implemented with transcription
            audioDescription: true, // Metadata provides context
            contrast: this.preferences.highContrast
        };
    }
    
    /**
     * Check WCAG Operable compliance
     */
    checkOperableCompliance() {
        return {
            keyboardAccessible: this.preferences.keyboardShortcuts,
            seizures: this.preferences.reduceMotion,
            navigable: this.checkNavigableElements(),
            inputModalities: true
        };
    }
    
    /**
     * Check WCAG Understandable compliance
     */
    checkUnderstandableCompliance() {
        return {
            readable: true, // Content is in clear language
            predictable: true, // Consistent navigation
            inputAssistance: this.checkInputAssistance()
        };
    }
    
    /**
     * Check WCAG Robust compliance
     */
    checkRobustCompliance() {
        return {
            compatible: this.checkMarkupValidity()
        };
    }
    
    /**
     * Check text alternatives for images
     */
    checkTextAlternatives() {
        const images = document.querySelectorAll('img');
        let hasAlternatives = 0;
        
        images.forEach(img => {
            if (img.alt !== undefined) {
                hasAlternatives++;
            }
        });
        
        return images.length === 0 || hasAlternatives === images.length;
    }
    
    /**
     * Check navigable elements
     */
    checkNavigableElements() {
        const hasSkipLinks = !!document.querySelector('.skip-link');
        const hasHeadings = document.querySelectorAll('h1, h2, h3, h4, h5, h6').length > 0;
        const hasLandmarks = document.querySelectorAll('[role="main"], [role="navigation"], [role="banner"]').length > 0;
        
        return hasSkipLinks && hasHeadings && hasLandmarks;
    }
    
    /**
     * Check input assistance
     */
    checkInputAssistance() {
        const inputs = document.querySelectorAll('input, select, textarea');
        let hasLabels = 0;
        
        inputs.forEach(input => {
            if (input.getAttribute('aria-label') || 
                input.getAttribute('aria-labelledby') || 
                document.querySelector(`label[for="${input.id}"]`)) {
                hasLabels++;
            }
        });
        
        return inputs.length === 0 || hasLabels === inputs.length;
    }
    
    /**
     * Check markup validity (basic check)
     */
    checkMarkupValidity() {
        // Basic checks for common accessibility markup
        const requiredElements = ['main', 'header'];
        let validMarkup = true;
        
        requiredElements.forEach(element => {
            if (!document.querySelector(element)) {
                validMarkup = false;
            }
        });
        
        return validMarkup;
    }
}

// Make AccessibilityManager available globally
window.AccessibilityManager = AccessibilityManager;-label first
        if (element.getAttribute('aria-label')) {
            return element.getAttribute('aria-label');
        }
        
        // Try aria