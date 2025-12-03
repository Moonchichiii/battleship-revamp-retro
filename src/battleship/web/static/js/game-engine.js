// static/js/game-engine.js

class TacticalSystems {
    constructor() {
        this.soundEnabled = false;
        this.audioCtx = null;
        this.timerInterval = null;
        this.secondsElapsed = 0;
        this.lastOut = 0; // For brown noise generation
        this.noiseNode = null;
        
        // SFX Synthesizer
        this.sounds = {
            fire: { freq: 150, type: 'sawtooth', duration: 0.1, vol: 0.1 },
            hit: { freq: 400, type: 'square', duration: 0.2, vol: 0.2 },
            miss: { freq: 100, type: 'triangle', duration: 0.3, vol: 0.1 },
            win: { type: 'custom-win' }
        };

        this.initListeners();
    }

    initListeners() {
        // 1. Sound Toggle
        document.addEventListener('click', (e) => {
            if (e.target.closest('#sound-toggle')) {
                this.toggleSound();
            }
        });

        // 2. HTMX After Swap (Detect Hit/Miss from HTML response)
        document.body.addEventListener('htmx:afterSwap', (evt) => {
            this.handleGameResponse(evt.detail.target);
        });
    }

    toggleSound() {
        this.soundEnabled = !this.soundEnabled;
        const btn = document.getElementById('sound-toggle');
        const icon = this.soundEnabled ? '🔊 ON' : '🔇 OFF';
        if (btn) btn.innerText = `AUDIO: ${icon}`;
        
        // Init Audio Context on first user gesture
        if (this.soundEnabled && !this.audioCtx) {
            this.audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        }
    }

    playSound(type) {
        if (!this.soundEnabled || !this.audioCtx) return;

        if (type === 'win') {
            this.playWinSequence();
            return;
        }

        const s = this.sounds[type];
        const osc = this.audioCtx.createOscillator();
        const gain = this.audioCtx.createGain();

        osc.type = s.type;
        osc.frequency.setValueAtTime(s.freq, this.audioCtx.currentTime);
        osc.frequency.exponentialRampToValueAtTime(0.01, this.audioCtx.currentTime + s.duration);

        gain.gain.setValueAtTime(s.vol, this.audioCtx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.01, this.audioCtx.currentTime + s.duration);

        osc.connect(gain);
        gain.connect(this.audioCtx.destination);
        osc.start();
        osc.stop(this.audioCtx.currentTime + s.duration);
    }

    playWinSequence() {
         // Simple Arpeggio
         [440, 554, 659, 880].forEach((freq, i) => {
                setTimeout(() => {
                     const osc = this.audioCtx.createOscillator();
                     const gain = this.audioCtx.createGain();
                     osc.type = 'square';
                     osc.frequency.value = freq;
                     gain.gain.value = 0.1;
                     gain.gain.exponentialRampToValueAtTime(0.01, this.audioCtx.currentTime + 0.3);
                     osc.connect(gain);
                     gain.connect(this.audioCtx.destination);
                     osc.start();
                     osc.stop(this.audioCtx.currentTime + 0.3);
                }, i * 150);
         });
    }

    playHover() {
        if (!this.soundEnabled || !this.audioCtx) return;
        const osc = this.audioCtx.createOscillator();
        const gain = this.audioCtx.createGain();
        
        osc.type = 'sine';
        osc.frequency.setValueAtTime(400, this.audioCtx.currentTime);
        osc.frequency.exponentialRampToValueAtTime(100, this.audioCtx.currentTime + 0.05);
        
        gain.gain.setValueAtTime(0.02, this.audioCtx.currentTime); // Very quiet
        gain.gain.exponentialRampToValueAtTime(0.001, this.audioCtx.currentTime + 0.05);
        
        osc.connect(gain);
        gain.connect(this.audioCtx.destination);
        osc.start();
        osc.stop(this.audioCtx.currentTime + 0.05);
    }

    startAmbience() {
        // Generates a 'Submarine Hum' using Brown Noise
        if (!this.soundEnabled || !this.audioCtx) return;
        const bufferSize = this.audioCtx.sampleRate * 2; // 2 seconds buffer
        const buffer = this.audioCtx.createBuffer(1, bufferSize, this.audioCtx.sampleRate);
        const data = buffer.getChannelData(0);

        for (let i = 0; i < bufferSize; i++) {
                // Brown noise approximation
                const white = Math.random() * 2 - 1;
                data[i] = (this.lastOut + (0.02 * white)) / 1.02;
                this.lastOut = data[i];
                data[i] *= 3.5; 
        }

        this.noiseNode = this.audioCtx.createBufferSource();
        this.noiseNode.buffer = buffer;
        this.noiseNode.loop = true;
        
        const gain = this.audioCtx.createGain();
        gain.gain.value = 0.05; // Low volume background
        
        this.noiseNode.connect(gain);
        gain.connect(this.audioCtx.destination);
        this.noiseNode.start();
    }

    // --- TIMER LOGIC ---
    startTimer() {
        this.stopTimer();
        this.secondsElapsed = 0;
        this.updateTimerDisplay();
        this.timerInterval = setInterval(() => {
                this.secondsElapsed++;
                this.updateTimerDisplay();
        }, 1000);
    }

    stopTimer() {
        if (this.timerInterval) clearInterval(this.timerInterval);
    }

    updateTimerDisplay() {
        const el = document.getElementById('game-timer');
        if (!el) return;
        const m = Math.floor(this.secondsElapsed / 60).toString().padStart(2, '0');
        const s = (this.secondsElapsed % 60).toString().padStart(2, '0');
        el.innerText = `${m}:${s}`;
    }

    // --- PARSING HTMX RESPONSE ---
    handleGameResponse(target) {
         // Start timer if new game
         if (target.id === 'main' || target.id === 'boardSection') {
                 if (document.querySelector('.cell:not(.hit):not(.miss)')) {
                         if (!this.timerInterval) this.startTimer();
                 }
         }
         
         // Check for signals embedded in the HTML response
         // We look for specific classes or text content added by Python
         const statusLog = document.getElementById('status');
         if (statusLog) {
                 const text = statusLog.innerText.toLowerCase();
                 if (text.includes('hit')) this.playSound('hit');
                 else if (text.includes('miss')) this.playSound('miss');
                 
                 if (text.includes('victory') || text.includes('game over')) {
                         this.stopTimer();
                         if (text.includes('victory')) this.playSound('win');
                 }
         }
    }
}

// Initialize
window.tacticalSys = new TacticalSystems();