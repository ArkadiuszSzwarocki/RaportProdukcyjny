/* ─── Scanner Sound and Audio Feedback ────────────────────── */
const AudioContextClass = window.AudioContext || window.webkitAudioContext;
let scannerAudioCtx = null;

function getScannerAudioContext() {
  if (!scannerAudioCtx && AudioContextClass) {
    scannerAudioCtx = new AudioContextClass();
  }
  return scannerAudioCtx;
}

function playBeep(type) {
  const ctx = getScannerAudioContext();
  if (!ctx) return;
  try {
    if (ctx.state === 'suspended') ctx.resume();
    const osc = ctx.createOscillator();
    const gainNode = ctx.createGain();
    osc.connect(gainNode);
    gainNode.connect(ctx.destination);

    if (type === 'success') {
      osc.type = 'sine';
      osc.frequency.setValueAtTime(800, ctx.currentTime);
      osc.frequency.exponentialRampToValueAtTime(1200, ctx.currentTime + 0.1);
      gainNode.gain.setValueAtTime(0.3, ctx.currentTime);
      gainNode.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.1);
      osc.start(ctx.currentTime);
      osc.stop(ctx.currentTime + 0.1);
    } else {
      osc.type = 'sawtooth';
      osc.frequency.setValueAtTime(300, ctx.currentTime);
      osc.frequency.exponentialRampToValueAtTime(150, ctx.currentTime + 0.3);
      gainNode.gain.setValueAtTime(0.3, ctx.currentTime);
      gainNode.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.3);
      osc.start(ctx.currentTime);
      osc.stop(ctx.currentTime + 0.3);
    }
  } catch (e) {
    console.warn("Audio play failed", e);
  }
}

function showToast(msg, type) {
  playBeep(type);
  const container = document.getElementById('toast-container');
  if (!container) return;

  const el = document.createElement('div');
  el.className = 'toast-msg';
  
  const colors = {success:'#166534', warn:'#92400e', danger:'#991b1b', info:'#0284c7'};
  el.style.background = colors[type] || '#0f172a';
  el.innerHTML = msg;

  container.appendChild(el);

  setTimeout(() => {
    el.style.opacity = '0';
    setTimeout(() => {
      if (el.parentNode) el.parentNode.removeChild(el);
    }, 500);
  }, 10000);
}
