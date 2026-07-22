// ---- splash: one loop of the Stake Engine loader, then the Monstrums sting ----
// Always auto-proceeds: plays the sting with audio when the browser allows it,
// silently falls back to muted autoplay when it doesn't.
(function splash() {
  var el = document.getElementById('splash');
  var vid = document.getElementById('splashVideo');
  var loaderImg = document.getElementById('splashLoader');
  var over = false;
  function dismiss() {
    if (over) return;
    over = true;
    try { vid.pause(); } catch (e) { /* ignore */ }
    el.classList.add('fade');
    setTimeout(function () { el.remove(); }, 600);
  }
  function stingStarted() {
    el.addEventListener('click', dismiss); // tap to skip
  }
  // Staged handover so the ground change is never a visible snap:
  // loader fades out (350ms) → ground eases #041721 → #000 (500ms) → sting
  // fades in and starts. Total ~0.9s of choreography between the two marks.
  function trySting() {
    loaderImg.classList.add('out');            // 1. fade the loader away
    setTimeout(function () {
      loaderImg.classList.add('hidden');
      el.classList.add('sting');               // 2. ease the ground to black
    }, 380);
    setTimeout(function () {
      vid.classList.remove('hidden');
      var p = vid.play(); // with audio, when the autoplay policy allows it
      var reveal = function () {
        void vid.offsetWidth; // commit the un-hide first, so the fade actually runs
        vid.classList.add('in');               // 3. fade the sting in
        stingStarted();
      };
      if (p && p.then) {
        p.then(reveal).catch(function () {
          vid.muted = true; // no gesture yet — proceed silently instead of gating
          vid.play().then(reveal).catch(dismiss);
        });
      } else {
        reveal();
      }
    }, 900);
  }
  vid.addEventListener('ended', dismiss);
  vid.addEventListener('error', dismiss);
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') dismiss(); });
  // preload="none" in markup keeps the sting off the critical path; start
  // fetching it once the loader phase is underway and game boot has begun
  setTimeout(function () { try { vid.load(); } catch (e) { /* ignore */ } }, 300);
  setTimeout(trySting, 2200);   // one full loader loop (the gif runs ~2.1s)
  setTimeout(dismiss, 20000);   // failsafe: never trap the player on the splash
})();
