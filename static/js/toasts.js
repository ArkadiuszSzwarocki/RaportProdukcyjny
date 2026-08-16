// Shared toast helper

/* ─── Audio Notifications ─────────────────────────────────── */
var AudioContextCls = window.AudioContext || window.webkitAudioContext;
var globalAudioCtx = AudioContextCls ? new AudioContextCls() : null;

function playToastBeep(type) {
  if (!globalAudioCtx) return;
  try {
    if (globalAudioCtx.state === 'suspended') globalAudioCtx.resume();
    var osc = globalAudioCtx.createOscillator();
    var gainNode = globalAudioCtx.createGain();
    osc.connect(gainNode);
    gainNode.connect(globalAudioCtx.destination);

    if (type === 'success') {
      osc.type = 'sine';
      osc.frequency.setValueAtTime(800, globalAudioCtx.currentTime);
      osc.frequency.exponentialRampToValueAtTime(1200, globalAudioCtx.currentTime + 0.1);
      gainNode.gain.setValueAtTime(0.3, globalAudioCtx.currentTime);
      gainNode.gain.exponentialRampToValueAtTime(0.01, globalAudioCtx.currentTime + 0.1);
      osc.start(globalAudioCtx.currentTime);
      osc.stop(globalAudioCtx.currentTime + 0.1);
    } else if (type === 'warning' || type === 'danger' || type === 'error') {
      osc.type = 'sawtooth';
      osc.frequency.setValueAtTime(300, globalAudioCtx.currentTime);
      osc.frequency.exponentialRampToValueAtTime(150, globalAudioCtx.currentTime + 0.3);
      gainNode.gain.setValueAtTime(0.3, globalAudioCtx.currentTime);
      gainNode.gain.exponentialRampToValueAtTime(0.01, globalAudioCtx.currentTime + 0.3);
      osc.start(globalAudioCtx.currentTime);
      osc.stop(globalAudioCtx.currentTime + 0.3);
    }
  } catch (e) {
    console.warn("Audio play failed", e);
  }
}

function showToast(message, type){
  playToastBeep(type);
  try{
    var container = document.getElementById('toastContainer');
    if(!container){
      container = document.createElement('div');
      container.id = 'toastContainer';
      container.setAttribute('aria-live','polite');
      container.setAttribute('aria-atomic','true');
      document.body.appendChild(container);
    }
    var d = document.createElement('div'); 
    d.className = 'toast ' + (type||'info'); 
    d.style.display = 'flex';
    d.style.alignItems = 'center';
    d.style.justifyContent = 'space-between';
    
    var textSpan = document.createElement('span');
    textSpan.textContent = message;
    textSpan.style.flex = '1';
    d.appendChild(textSpan);
    
    var closeBtn = document.createElement('button');
    closeBtn.innerHTML = '&times;';
    closeBtn.style.background = 'transparent';
    closeBtn.style.border = 'none';
    closeBtn.style.color = 'inherit';
    closeBtn.style.fontSize = '1.2em';
    closeBtn.style.lineHeight = '1';
    closeBtn.style.cursor = 'pointer';
    closeBtn.style.marginLeft = '12px';
    closeBtn.style.padding = '0 4px';
    closeBtn.style.opacity = '0.7';
    closeBtn.onmouseover = function() { closeBtn.style.opacity = '1'; };
    closeBtn.onmouseout = function() { closeBtn.style.opacity = '0.7'; };
    
    closeBtn.onclick = function() {
      d.style.transition='opacity 0.25s'; 
      d.style.opacity='0'; 
      setTimeout(function(){ d.remove(); },250);
    };
    
    d.appendChild(closeBtn);
    container.appendChild(d);
  }catch(e){ if(window && window.console) console.error('showToast error', e); }
}
