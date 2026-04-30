(function (global) {
  'use strict';
  var _audioCtx = null;
  function getCtx() {
    if (_audioCtx) return _audioCtx;
    try {
      _audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    } catch (e) {
      _audioCtx = null;
    }
    return _audioCtx;
  }

  function playDoorbell() {
    var ctx = getCtx();
    if (!ctx) return false;
    var now = ctx.currentTime;
    var master = ctx.createGain();
    master.gain.setValueAtTime(1.0, now);
    master.connect(ctx.destination);

    // Sequence of bell-like partials
    var seq = [
      { f: 880, t: 0.00, d: 0.38 },
      { f: 1320, t: 0.18, d: 0.42 },
      { f: 990, t: 0.42, d: 0.46 }
    ];

    seq.forEach(function(it){
      try {
        var o = ctx.createOscillator();
        var g = ctx.createGain();
        o.type = 'sine';
        o.frequency.setValueAtTime(it.f, now + it.t);
        g.gain.setValueAtTime(0.0001, now + it.t);
        g.gain.linearRampToValueAtTime(0.9, now + it.t + 0.01);
        g.gain.exponentialRampToValueAtTime(0.0001, now + it.t + it.d);
        o.connect(g); g.connect(master);
        o.start(now + it.t);
        o.stop(now + it.t + it.d + 0.05);
      } catch (e) { /* ignore */ }
    });

    // small noise click at the start to make it more 'real'
    try {
      var noiseDur = 0.02;
      var buf = ctx.createBuffer(1, Math.floor(ctx.sampleRate * noiseDur), ctx.sampleRate);
      var data = buf.getChannelData(0);
      for (var i = 0; i < data.length; i++) {
        data[i] = (Math.random() * 2 - 1) * Math.exp(-i / (ctx.sampleRate * noiseDur));
      }
      var src = ctx.createBufferSource();
      src.buffer = buf;
      var ng = ctx.createGain(); ng.gain.setValueAtTime(0.08, now);
      src.connect(ng); ng.connect(master);
      src.start(now);
      src.stop(now + noiseDur + 0.01);
    } catch (e) { /* ignore */ }

    return true;
  }

  global.playZwolnienieSound = function() {
    try {
      var ctx = getCtx();
      if (ctx && ctx.state === 'suspended' && typeof ctx.resume === 'function') {
        ctx.resume().catch(function(){});
      }
      return playDoorbell();
    } catch (e) {
      console.warn('playZwolnienieSound failed:', e);
      return false;
    }
  };

  // Install one-time listeners to try to resume AudioContext on first user gesture.
  try {
    var _unlockHandler = function() {
      try {
        var _c = getCtx();
        if (_c && _c.state === 'suspended' && typeof _c.resume === 'function') {
          _c.resume().catch(function(){});
        }
      } catch (e) {}
      try { document.removeEventListener('click', _unlockHandler); } catch (e) {}
      try { document.removeEventListener('keydown', _unlockHandler); } catch (e) {}
      try { document.removeEventListener('touchstart', _unlockHandler); } catch (e) {}
    };
    document.addEventListener('click', _unlockHandler, { passive: true });
    document.addEventListener('keydown', _unlockHandler, { passive: true });
    document.addEventListener('touchstart', _unlockHandler, { passive: true });
  } catch (e) {
    // ignore
  }

})(window);
