// Typography control functions
class TypographyManager {
    constructor() {
        this.loadSavedPreferences();
    }
    
    adjustFontSize(size) {
        const body = document.body;
        
        // Remove existing size classes
        body.classList.remove('font-size-small', 'font-size-medium', 'font-size-large', 'font-size-x-large', 'font-size-xx-large');
        
        // Add new size class
        body.classList.add(`font-size-${size}`);
        
        // Save preference
        this.savePreference('fontSize', size);
        
        // Emit event for other components
        window.dispatchEvent(new CustomEvent('fontSizeChanged', { detail: { size } }));
    }
    
    toggleHighContrast(enabled) {
        const body = document.body;
        
        if (enabled) {
            body.classList.add('high-contrast');
        } else {
            body.classList.remove('high-contrast');
        }
        
        this.savePreference('highContrast', enabled);
    }
    
    savePreference(key, value) {
        try {
            const prefs = JSON.parse(localStorage.getItem('typographyPrefs') || '{}');
            prefs[key] = value;
            localStorage.setItem('typographyPrefs', JSON.stringify(prefs));
        } catch (e) {
            console.log('Could not save typography preference:', e);
        }
    }
    
    loadSavedPreferences() {
        try {
            const prefs = JSON.parse(localStorage.getItem('typographyPrefs') || '{}');
            
            if (prefs.fontSize) {
                this.adjustFontSize(prefs.fontSize);
            }
            
            if (prefs.highContrast) {
                this.toggleHighContrast(prefs.highContrast);
            }
        } catch (e) {
            console.log('Could not load typography preferences:', e);
        }
    }
}

// Initialize typography manager when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.typographyManager = new TypographyManager();
});






// Enhanced Font Size Controls for Opulent Voice Interface
// Add this to your html5_gui/js/typography.js file

class OpulentVoiceFontManager {
    constructor() {
        this.defaultSize = 16;
        this.minSize = 12;
        this.maxSize = 28;
        this.scaleFactor = 1.15; // 15% increase/decrease per step
        this.currentSize = this.defaultSize;
        
        this.init();
    }
    
    init() {
        // Load saved preference
        this.loadSavedPreference();
        
        // Apply initial font size
        this.applyFontSize(this.currentSize);
        
        // Set up keyboard shortcuts
        this.setupKeyboardShortcuts();
        
        // Initialize UI controls if they exist
        this.initializeControls();
        
        console.log('🎯 Opulent Voice Font Manager initialized');
    }
    
    // Font size adjustment methods
    increaseFontSize() {
        const newSize = Math.min(this.currentSize * this.scaleFactor, this.maxSize);
        if (newSize !== this.currentSize) {
            this.setFontSize(newSize);
            this.announceChange('increased', newSize);
        }
    }
    
    decreaseFontSize() {
        const newSize = Math.max(this.currentSize / this.scaleFactor, this.minSize);
        if (newSize !== this.currentSize) {
            this.setFontSize(newSize);
            this.announceChange('decreased', newSize);
        }
    }
    
    resetFontSize() {
        this.setFontSize(this.defaultSize);
        this.announceChange('reset', this.defaultSize);
    }
    
    setFontSize(size) {
        this.currentSize = size;
        this.applyFontSize(size);
        this.savePreference(size);
        this.updateUI();
    }
    
    applyFontSize(size) {
        // Set root font size for rem-based scaling
        document.documentElement.style.fontSize = size + 'px';
        
        // Also set CSS custom property for more control
        document.documentElement.style.setProperty('--base-font-size', size + 'px');
        
        // Trigger custom event for other components
        window.dispatchEvent(new CustomEvent('fontSizeChanged', { 
            detail: { size: size, percentage: Math.round((size / this.defaultSize) * 100) }
        }));
    }
    
    // Accessibility announcements
    announceChange(action, size) {
        const percentage = Math.round((size / this.defaultSize) * 100);
        let message = '';
        
        switch(action) {
            case 'increased':
                message = `Font size increased to ${percentage}%`;
                break;
            case 'decreased':
                message = `Font size decreased to ${percentage}%`;
                break;
            case 'reset':
                message = `Font size reset to default`;
                break;
        }
        
        // Visual notification
        this.showNotification(message);
        
        // Screen reader announcement
        this.announceToScreenReader(message);
    }
    
    showNotification(message) {
        // Create temporary notification
        const notification = document.createElement('div');
        notification.className = 'font-size-notification';
        notification.textContent = message;
        notification.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            background: rgba(0, 150, 255, 0.9);
            color: white;
            padding: 10px 15px;
            border-radius: 6px;
            font-family: 'Atkinson Hyperlegible', Arial, sans-serif;
            font-size: 14px;
            z-index: 10000;
            backdrop-filter: blur(10px);
            transition: opacity 0.3s ease;
        `;
        
        document.body.appendChild(notification);
        
        // Remove after 2 seconds
        setTimeout(() => {
            notification.style.opacity = '0';
            setTimeout(() => notification.remove(), 300);
        }, 2000);
    }
    
    announceToScreenReader(message) {
        // Create aria-live region for screen readers
        let announcer = document.getElementById('font-size-announcer');
        if (!announcer) {
            announcer = document.createElement('div');
            announcer.id = 'font-size-announcer';
            announcer.setAttribute('aria-live', 'polite');
            announcer.setAttribute('aria-atomic', 'true');
            announcer.style.cssText = `
                position: absolute;
                left: -10000px;
                width: 1px;
                height: 1px;
                overflow: hidden;
            `;
            document.body.appendChild(announcer);
        }
        
        announcer.textContent = message;
    }
    
    // Keyboard shortcuts
    setupKeyboardShortcuts() {
        document.addEventListener('keydown', (e) => {
            // Ctrl/Cmd + Plus/Equals for increase
            if ((e.ctrlKey || e.metaKey) && (e.key === '+' || e.key === '=')) {
                e.preventDefault();
                this.increaseFontSize();
            }
            
            // Ctrl/Cmd + Minus for decrease
            if ((e.ctrlKey || e.metaKey) && e.key === '-') {
                e.preventDefault();
                this.decreaseFontSize();
            }
            
            // Ctrl/Cmd + 0 for reset
            if ((e.ctrlKey || e.metaKey) && e.key === '0') {
                e.preventDefault();
                this.resetFontSize();
            }
        });
    }
    
    // UI Controls
    initializeControls() {
        // Create font controls if they don't exist
        this.createFontControls();
        
        // Update existing controls
        this.updateUI();
    }
    
    createFontControls() {
        // Look for existing controls
        let controlsContainer = document.getElementById('font-size-controls');
        
        if (!controlsContainer) {
            // Create controls container
            controlsContainer = document.createElement('div');
            controlsContainer.id = 'font-size-controls';
            controlsContainer.className = 'font-controls';
            controlsContainer.innerHTML = `
                <div class="font-control-group" role="toolbar" aria-label="Font size controls">
                    <label class="font-control-label">Text Size:</label>
                    <button id="font-decrease" class="font-control-btn" aria-label="Decrease font size" title="Decrease font size (Ctrl+-)">
                        <span class="font-icon">A-</span>
                    </button>
                    <button id="font-reset" class="font-control-btn" aria-label="Reset font size to default" title="Reset font size (Ctrl+0)">
                        <span class="font-icon">A</span>
                    </button>
                    <button id="font-increase" class="font-control-btn" aria-label="Increase font size" title="Increase font size (Ctrl++)">
                        <span class="font-icon">A+</span>
                    </button>
                    <span id="font-size-indicator" class="font-size-indicator" aria-live="polite">100%</span>
                </div>
            `;
            
            // Add CSS styles
            const styles = document.createElement('style');
            styles.textContent = `
                .font-controls {
                    display: flex;
                    align-items: center;
                    gap: 8px;
                    padding: 8px;
                    background: rgba(255, 255, 255, 0.1);
                    backdrop-filter: blur(10px);
                    border-radius: 8px;
                    border: 1px solid rgba(255, 255, 255, 0.2);
                    font-family: 'Atkinson Hyperlegible', Arial, sans-serif;
                }
                
                .font-control-group {
                    display: flex;
                    align-items: center;
                    gap: 6px;
                }
                
                .font-control-label {
                    font-size: 0.9rem;
                    color: #ffffff;
                    margin-right: 4px;
                }
                
                .font-control-btn {
                    background: rgba(255, 255, 255, 0.2);
                    border: 1px solid rgba(255, 255, 255, 0.3);
                    border-radius: 4px;
                    color: #ffffff;
                    cursor: pointer;
                    padding: 6px 10px;
                    font-family: 'Atkinson Hyperlegible', Arial, sans-serif;
                    font-size: 14px;
                    font-weight: 600;
                    transition: all 0.2s ease;
                    min-width: 36px;
                }
                
                .font-control-btn:hover {
                    background: rgba(255, 255, 255, 0.3);
                    border-color: rgba(255, 255, 255, 0.5);
                    transform: translateY(-1px);
                }
                
                .font-control-btn:active {
                    transform: translateY(0);
                    background: rgba(255, 255, 255, 0.4);
                }
                
                .font-control-btn:focus {
                    outline: 2px solid #00ff88;
                    outline-offset: 2px;
                }
                
                .font-size-indicator {
                    font-size: 0.85rem;
                    color: #00ff88;
                    font-weight: 600;
                    min-width: 40px;
                    text-align: center;
                }
                
                .font-icon {
                    display: inline-block;
                }
                
                /* High contrast mode support */
                .high-contrast .font-control-btn {
                    background: #000000;
                    border-color: #ffffff;
                    color: #ffffff;
                }
                
                .high-contrast .font-control-btn:hover {
                    background: #333333;
                }
            `;
            document.head.appendChild(styles);
            
            // Find a good place to insert the controls
            this.insertControlsInUI(controlsContainer);
        }
        
        // Attach event listeners
        this.attachControlEvents();
    }
    
    insertControlsInUI(controlsContainer) {
        // Try to find the best place to insert font controls
        const candidates = [
            '.transcription-controls',
            '.ui-controls',
            '.header-controls',
            'header',
            'nav',
            '.toolbar'
        ];
        
        let insertTarget = null;
        for (const selector of candidates) {
            insertTarget = document.querySelector(selector);
            if (insertTarget) break;
        }
        
        if (insertTarget) {
            insertTarget.appendChild(controlsContainer);
        } else {
            // Fallback: create a floating control panel
            controlsContainer.style.cssText = `
                position: fixed;
                top: 20px;
                left: 20px;
                z-index: 9999;
            `;
            document.body.appendChild(controlsContainer);
        }
    }
    
    attachControlEvents() {
        const decreaseBtn = document.getElementById('font-decrease');
        const resetBtn = document.getElementById('font-reset');
        const increaseBtn = document.getElementById('font-increase');
        
        if (decreaseBtn) decreaseBtn.addEventListener('click', () => this.decreaseFontSize());
        if (resetBtn) resetBtn.addEventListener('click', () => this.resetFontSize());
        if (increaseBtn) increaseBtn.addEventListener('click', () => this.increaseFontSize());
    }
    
    updateUI() {
        const indicator = document.getElementById('font-size-indicator');
        if (indicator) {
            const percentage = Math.round((this.currentSize / this.defaultSize) * 100);
            indicator.textContent = percentage + '%';
        }
        
        // Update button states
        const decreaseBtn = document.getElementById('font-decrease');
        const increaseBtn = document.getElementById('font-increase');
        
        if (decreaseBtn) {
            decreaseBtn.disabled = this.currentSize <= this.minSize;
        }
        
        if (increaseBtn) {
            increaseBtn.disabled = this.currentSize >= this.maxSize;
        }
    }
    
    // Persistence
    savePreference(size) {
        try {
            localStorage.setItem('opulent-voice-font-size', size.toString());
        } catch (e) {
            console.warn('Could not save font size preference:', e);
        }
    }
    
    loadSavedPreference() {
        try {
            const saved = localStorage.getItem('opulent-voice-font-size');
            if (saved) {
                const size = parseFloat(saved);
                if (size >= this.minSize && size <= this.maxSize) {
                    this.currentSize = size;
                }
            }
        } catch (e) {
            console.warn('Could not load font size preference:', e);
        }
    }
    
    // API for other components
    getCurrentSize() {
        return this.currentSize;
    }
    
    getCurrentPercentage() {
        return Math.round((this.currentSize / this.defaultSize) * 100);
    }
    
    // Integration with configuration system
    applyConfigSettings(config) {
        if (config && config.gui && config.gui.accessibility) {
            const accessibility = config.gui.accessibility;
            
            // Apply font size from config
            if (accessibility.font_size) {
                const sizeMap = {
                    'small': 14,
                    'medium': 16,
                    'large': 18,
                    'x-large': 20,
                    'xx-large': 24
                };
                
                const configSize = sizeMap[accessibility.font_size];
                if (configSize) {
                    this.setFontSize(configSize);
                }
            }
            
            // Apply high contrast if enabled
            if (accessibility.high_contrast) {
                document.body.classList.add('high-contrast');
            }
        }
    }
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.opulentFontManager = new OpulentVoiceFontManager();
    
    // Listen for configuration updates from web interface
    window.addEventListener('configurationLoaded', (event) => {
        if (window.opulentFontManager && event.detail) {
            window.opulentFontManager.applyConfigSettings(event.detail);
        }
    });
    
    console.log('🎯 Opulent Voice font size controls ready!');
});
