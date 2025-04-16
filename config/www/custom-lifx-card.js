class CustomLifxCard extends HTMLElement {
    setConfig(config) {
        if (!config.entity) {
            throw new Error('Entity not defined');
        }
        this._config = { ...config }; 
        this.loadState(); 
        this.render(); 
    }

    set hass(hass) {
        this._hass = hass; 
        this.render(); 
    }

    render() {
        if (!this._config || !this._hass) {
            return; 
        }

        const sunriseTime = this._hass.states['sun.sun'].attributes.next_rising;
        const sunsetTime = this._hass.states['sun.sun'].attributes.next_setting;

        this.innerHTML = `
            <ha-card header="Sun Automation">
                <div class="card-content">
                    <div class="sun-times">
                        <div class="sun-time" id="sunrise-time">
                            <div class="dot ${this._config.sunriseEnabled ? '' : 'hidden'}" id="sunrise-dot"></div>
                            <ha-icon icon="mdi:weather-sunset-up" class="sun-icon"></ha-icon>
                            <span class="sunrise-text">Actual Sunrise: ${this.formatTime(sunriseTime)}</span>
                        </div>
                        <div class="sun-time" id="sunset-time">
                            <div class="dot ${this._config.sunsetEnabled ? '' : 'hidden'}" id="sunset-dot"></div>
                            <ha-icon icon="mdi:weather-sunset-down" class="sun-icon"></ha-icon>
                            <span class="sunset-text">Actual Sunset: ${this.formatTime(sunsetTime)}</span>
                        </div>
                    </div>
                    <div id="sunrise-settings" class="sun-settings hidden">
                        <h4>Sunrise:</h4>
                        <label>
                            <input type="checkbox" id="sunrise-switch" ${this._config.sunriseEnabled ? 'checked' : ''}>
                            Turn on at Sunrise
                        </label>
                        <div class="slider-container">
                            <input type="range" id="sunrise-offset" min="-60" max="60" value="${this._config.sunriseOffset || 0}" step="1">
                            <span id="sunrise-offset-value">${this._config.sunriseOffset || 0}</span> min
                        </div>
                    </div>
                    <div id="sunset-settings" class="sun-settings hidden">
                        <h4>Sunset:</h4>
                        <label>
                            <input type="checkbox" id="sunset-switch" ${this._config.sunsetEnabled ? 'checked' : ''}>
                            Turn on at Sunset
                        </label>
                        <div class="slider-container">
                            <input type="range" id="sunset-offset" min="-60" max="60" value="${this._config.sunsetOffset || 0}" step="1">
                            <span id="sunset-offset-value">${this._config.sunsetOffset || 0}</span> min
                        </div>
                    </div>
                </div>
                <style>
                    ha-card {
                        box-shadow: none; /* Remove default shadow */
                        border-radius: 10px; /* Rounded corners for the card */
                        overflow: hidden; /* Hide overflow */
                        background: var(--ha-card-background); /* Match system background color */
                        border: 1px solid var(--primary-border-color, #ccc); /* Ensure a visible border color */
                    }
                    .card-content {
                        padding: 16px; /* Padding inside the card */
                    }
                    .sun-times {
                        display: flex; /* Use flexbox to display sunrise and sunset times */
                        justify-content: space-between; /* Space between the two elements */
                        margin-bottom: 16px; /* Spacing below the sun times */
                    }
                    .sun-time {
                        background-color: var(--ha-card-background); /* Match system background color */
                        border-radius: 25px; /* Rounded corners for pill shape */
                        padding: 10px 15px; /* Padding for pill shape */
                        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2); /* Subtle shadow */
                        display: flex; /* Flexbox for aligning items */
                        align-items: center; /* Align items in the center */
                        font-size: 14px; /* Font size for time display */
                        cursor: pointer; /* Show cursor pointer on hover */
                        position: relative; /* For positioning the dot */
                    }
                    .sun-icon {
                        margin-left: 8px; /* Space between icon and text */
                        color: var(--primary-color); /* Match the icon color with primary theme color */
                    }
                    .dot {
                        width: 6px; /* Width of the dot (smaller size) */
                        height: 6px; /* Height of the dot (smaller size) */
                        border-radius: 50%; /* Make the dot round */
                        background-color: orange; /* Dot color */
                        position: absolute; /* Position the dot */
                        left: 10px; /* Align dot to the left */
                        top: 50%; /* Center dot vertically */
                        transform: translateY(-50%); /* Adjust for vertical centering */
                    }
                    .sun-settings {
                        margin: 16px 0; /* Margin for sun settings section */
                    }
                    .sun-settings h4 {
                        margin: 8px 0; /* Margin for headings */
                    }
                    .hidden {
                        display: none; /* Class to hide elements */
                    }
                    input[type="range"] {
                        width: 100%; /* Full width for the slider */
                    }
                    .slider-container {
                        display: flex; /* Use flexbox for the slider container */
                        align-items: center; /* Align items in the center */
                        margin-top: 8px; /* Margin above the slider */
                    }
                    .slider-container span {
                        margin-left: 10px; /* Space between slider and value text */
                        font-weight: bold; /* Bold value text */
                    }
                    input[type="checkbox"] {
                        margin-right: 8px; /* Space after checkbox */
                    }
                </style>
            </ha-card>
        `;

        this.querySelector('#sunrise-time').onclick = () => {
            const sunriseSettings = this.querySelector('#sunrise-settings');
            const sunsetSettings = this.querySelector('#sunset-settings');
            sunriseSettings.classList.toggle('hidden'); 
            sunsetSettings.classList.add('hidden'); 
        };

        this.querySelector('#sunset-time').onclick = () => {
            const sunsetSettings = this.querySelector('#sunset-settings');
            const sunriseSettings = this.querySelector('#sunrise-settings');
            sunsetSettings.classList.toggle('hidden'); 
            sunriseSettings.classList.add('hidden'); 
        };

        // Sunrise switch
        const sunriseSwitch = this.querySelector('#sunrise-switch');
        const sunriseDot = this.querySelector('#sunrise-dot');
        sunriseSwitch.onchange = (e) => {
            this._config.sunriseEnabled = e.target.checked; 
            sunriseDot.classList.toggle('hidden', !e.target.checked); 
            if (e.target.checked) {
                this.checkSunriseTime();
            } else {
                this.resetSunriseOffset(); 
            }
            this.updateOffsets(); 
            this.saveState(); 
        };

        // Sunrise offset slider change
        const sunriseOffsetSlider = this.querySelector('#sunrise-offset');
        sunriseOffsetSlider.oninput = (e) => {
            const offset = parseInt(e.target.value, 10);
            this._config.sunriseOffset = offset; 
            this.querySelector('#sunrise-offset-value').textContent = offset; 
            sunriseSwitch.checked = true; 
            sunriseDot.classList.remove('hidden');

            this.saveState();
        };

        // Sunset switch
        const sunsetSwitch = this.querySelector('#sunset-switch');
        const sunsetDot = this.querySelector('#sunset-dot');
        sunsetSwitch.onchange = (e) => {
            this._config.sunsetEnabled = e.target.checked; 
            sunsetDot.classList.toggle('hidden', !e.target.checked); 
            if (e.target.checked) {
                this.checkSunsetTime();
            } else {
                this.resetSunsetOffset(); 
            }
            this.updateOffsets(); 
            this.saveState(); 
        };

        // Sunset offset slider change
        const sunsetOffsetSlider = this.querySelector('#sunset-offset');
        sunsetOffsetSlider.oninput = (e) => {
            const offset = parseInt(e.target.value, 10);
            this._config.sunsetOffset = offset; 
            this.querySelector('#sunset-offset-value').textContent = offset; 
            sunsetSwitch.checked = true; 
            sunsetDot.classList.remove('hidden'); 
            this.saveState(); 
        };
        this.checkTimesPeriodically(); 
    }

    formatTime(dateString) {
        const date = new Date(dateString);
        return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }); // Format time as HH:MM
    }

    loadState() {
        const savedConfig = localStorage.getItem('custom_lifx_card_config');
        if (savedConfig) {
            this._config = { ...this._config, ...JSON.parse(savedConfig) }; 
        }
    }

    saveState() {
        localStorage.setItem('custom_lifx_card_config', JSON.stringify(this._config)); 
    }

    updateOffsets() {
        this.querySelector('#sunrise-offset').value = this._config.sunriseOffset || 0; 
        this.querySelector('#sunset-offset').value = this._config.sunsetOffset || 0; 
        this.querySelector('#sunrise-offset-value').textContent = this._config.sunriseOffset || 0; 
        this.querySelector('#sunset-offset-value').textContent = this._config.sunsetOffset || 0; 
    }

    resetSunriseOffset() {
        this._config.sunriseOffset = 0;
        this.updateOffsets(); 
    }

    resetSunsetOffset() {
        this._config.sunsetOffset = 0;
        this.updateOffsets();
    }

    checkTimesPeriodically() {
        setInterval(() => {
            this.checkSunriseTime(); 
            this.checkSunsetTime(); 
        }, 60000); // Check every minute
    }

    checkSunriseTime() {
        const sunriseTime = this._hass.states['sun.sun'].attributes.next_rising;
        const currentTime = new Date();
        const adjustedSunriseTime = new Date(sunriseTime);
        adjustedSunriseTime.setMinutes(adjustedSunriseTime.getMinutes() + (this._config.sunriseOffset || 0)); 

        if (
            this._config.sunriseEnabled &&
            currentTime.getHours() === adjustedSunriseTime.getHours() &&
            currentTime.getMinutes() === adjustedSunriseTime.getMinutes()
        ) {
            this.triggerLightSwitch(); 
        }
    }

    checkSunsetTime() {
        const sunsetTime = this._hass.states['sun.sun'].attributes.next_setting;
        const currentTime = new Date();
        const adjustedSunsetTime = new Date(sunsetTime);
        adjustedSunsetTime.setMinutes(adjustedSunsetTime.getMinutes() + (this._config.sunsetOffset || 0)); 

        if (
            this._config.sunsetEnabled &&
            currentTime.getHours() === adjustedSunsetTime.getHours() &&
            currentTime.getMinutes() === adjustedSunsetTime.getMinutes()
        ) {
            this.triggerLightSwitch(); 
        }
    }

    triggerLightSwitch() {
        this._hass.callService('input_boolean', 'turn_on', {
            entity_id: 'input_boolean.virtual_light' 
        });
    }
}

customElements.define('custom-lifx-card', CustomLifxCard);

