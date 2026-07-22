// ---------------------------------------------------------------- themes
// Each theme is a complete palette: canvas colors + the CSS variables the DOM
// shell uses. `multRGB`/`vigRGB` are raw r,g,b for alpha-composed fills.
var THEMES = {
  rose: {
    label: 'Terminal Rose',
    css: { bg: '#170a10', panel: '#0d0509', border: '#3a1c2a', text: '#f3e9ee',
           dim: '#8d7a84', accent: '#e8dd4e', accentText: '#4a4310',
           gain: '#7fe0a8', loss: '#ff8ba0', win: '#ffe94a', toastBg: 'rgba(20,9,14,0.92)' },
    bg: '#170a10', gridLine: 'rgba(214,116,152,0.13)', gridLineMajor: 'rgba(214,116,152,0.22)',
    axisText: 'rgba(233,190,206,0.75)', multRGB: '233,168,194',
    line: '#f6b9cf', lineGlow: 'rgba(246,148,183,0.9)', dot: '#ffffff',
    priceTagBg: '#c2447e', priceTagText: '#ffffff',
    chip1: '#f7f28c', chip2: '#e8dd4e', chipGlow: 'rgba(240,230,90,0.75)', betText: '#4a4310',
    hot1: '#ffb35c', hot2: '#f2853a', hotGlowRGB: '255,160,70',
    lossFill1: '#b03a50', lossFill2: '#7c2032', lossGlow: 'rgba(240,70,100,0.9)', lossText: '#ffe3e8',
    countTrack: 'rgba(74,32,10,0.55)', countFill: '#fff6c0', ring: '#fff6c0',
    winFloat: '#f5ee7a', lossFloat: '#ff6b81',
    hover: 'rgba(247,242,140,0.85)', hoverFill: 'rgba(247,242,140,0.10)', hoverText: 'rgba(255,246,192,0.95)',
    reject: '#f0506a', deadZone: 'rgba(23,10,16,0.55)', nowLine: 'rgba(246,185,207,0.35)',
    vigRGB: '255,220,90'
  },
  neon: {
    label: 'Neon Green',
    css: { bg: '#070B10', panel: '#0D1420', border: '#1A222C', text: '#E6E8EC',
           dim: '#79828d', accent: '#39FF6A', accentText: '#04120a',
           gain: '#39FF6A', loss: '#ff7a94', win: '#B9FF7A', toastBg: 'rgba(10,16,22,0.92)' },
    bg: '#070B10', gridLine: 'rgba(57,255,106,0.10)', gridLineMajor: 'rgba(57,255,106,0.18)',
    axisText: 'rgba(230,232,236,0.65)', multRGB: '150,230,170',
    line: '#39FF6A', lineGlow: 'rgba(57,255,106,0.85)', dot: '#ffffff',
    priceTagBg: '#39FF6A', priceTagText: '#04120a',
    chip1: '#B9FF7A', chip2: '#39FF6A', chipGlow: 'rgba(57,255,106,0.7)', betText: '#06250f',
    hot1: '#f8ff6a', hot2: '#d7f23a', hotGlowRGB: '215,255,90',
    lossFill1: '#e0405a', lossFill2: '#8c1f33', lossGlow: 'rgba(255,80,110,0.9)', lossText: '#ffe3e8',
    countTrack: 'rgba(6,37,15,0.55)', countFill: '#eaffdd', ring: '#eaffdd',
    winFloat: '#B9FF7A', lossFloat: '#ff6b81',
    hover: 'rgba(57,255,106,0.85)', hoverFill: 'rgba(57,255,106,0.10)', hoverText: 'rgba(200,255,210,0.95)',
    reject: '#ff5c7a', deadZone: 'rgba(7,11,16,0.55)', nowLine: 'rgba(57,255,106,0.35)',
    vigRGB: '57,255,106'
  },
  cyber: {
    label: 'Cyberpunk',
    css: { bg: '#0b0906', panel: '#120d08', border: '#33231a', text: '#f4ede4',
           dim: '#9a8a78', accent: '#ff8a1f', accentText: '#3a1c02',
           gain: '#2ee6d6', loss: '#ff7a94', win: '#ffcf7a', toastBg: 'rgba(18,13,8,0.92)' },
    bg: '#0b0906', gridLine: 'rgba(255,140,60,0.12)', gridLineMajor: 'rgba(255,140,60,0.20)',
    axisText: 'rgba(255,214,170,0.7)', multRGB: '255,180,120',
    line: '#2ee6d6', lineGlow: 'rgba(46,230,214,0.85)', dot: '#ffffff',
    priceTagBg: '#0fb8a9', priceTagText: '#02201d',
    chip1: '#ffb35c', chip2: '#ff8a1f', chipGlow: 'rgba(255,150,60,0.75)', betText: '#3a1c02',
    hot1: '#ff7a45', hot2: '#ff4d2e', hotGlowRGB: '255,90,50',
    lossFill1: '#c22a4e', lossFill2: '#7c1030', lossGlow: 'rgba(255,70,100,0.9)', lossText: '#ffe3e8',
    countTrack: 'rgba(60,20,4,0.55)', countFill: '#ffe9c9', ring: '#ffe9c9',
    winFloat: '#ffcf7a', lossFloat: '#ff6b81',
    hover: 'rgba(46,230,214,0.85)', hoverFill: 'rgba(46,230,214,0.10)', hoverText: 'rgba(190,255,248,0.95)',
    reject: '#ff4d6d', deadZone: 'rgba(11,9,6,0.55)', nowLine: 'rgba(46,230,214,0.35)',
    vigRGB: '255,170,60'
  },
  light: {
    label: 'Light Minimal',
    css: { bg: '#f5f6f8', panel: '#ffffff', border: '#dfe3ea', text: '#1c2430',
           dim: '#7a8494', accent: '#2563eb', accentText: '#ffffff',
           gain: '#0f9d58', loss: '#d6335c', win: '#b7791f', toastBg: 'rgba(255,255,255,0.95)' },
    bg: '#f5f6f8', gridLine: 'rgba(28,36,48,0.07)', gridLineMajor: 'rgba(28,36,48,0.13)',
    axisText: 'rgba(28,36,48,0.6)', multRGB: '70,90,120',
    line: '#2563eb', lineGlow: 'rgba(37,99,235,0.35)', dot: '#1c2430',
    priceTagBg: '#2563eb', priceTagText: '#ffffff',
    chip1: '#ffe27a', chip2: '#f5c518', chipGlow: 'rgba(245,197,24,0.5)', betText: '#4a3a05',
    hot1: '#ffb35c', hot2: '#f2853a', hotGlowRGB: '242,133,58',
    lossFill1: '#e35d75', lossFill2: '#c22a4e', lossGlow: 'rgba(226,60,90,0.6)', lossText: '#ffffff',
    countTrack: 'rgba(74,58,5,0.25)', countFill: '#6b5305', ring: '#b8860b',
    winFloat: '#b7791f', lossFloat: '#d6335c',
    hover: 'rgba(37,99,235,0.8)', hoverFill: 'rgba(37,99,235,0.08)', hoverText: 'rgba(30,64,175,0.95)',
    reject: '#d6335c', deadZone: 'rgba(245,246,248,0.6)', nowLine: 'rgba(28,36,48,0.3)',
    vigRGB: '245,197,24'
  },
  dark: {
    label: 'Dark Mode',
    css: { bg: '#121417', panel: '#1a1d21', border: '#2a2e34', text: '#e8eaed',
           dim: '#8b929b', accent: '#4c8bf5', accentText: '#ffffff',
           gain: '#4ade80', loss: '#f87171', win: '#e3b341', toastBg: 'rgba(26,29,33,0.94)' },
    bg: '#121417', gridLine: 'rgba(140,150,165,0.10)', gridLineMajor: 'rgba(140,150,165,0.18)',
    axisText: 'rgba(200,205,212,0.65)', multRGB: '150,160,175',
    line: '#4c8bf5', lineGlow: 'rgba(76,139,245,0.7)', dot: '#ffffff',
    priceTagBg: '#4c8bf5', priceTagText: '#ffffff',
    chip1: '#f4d35e', chip2: '#e3b341', chipGlow: 'rgba(227,179,65,0.6)', betText: '#3a2c05',
    hot1: '#ff9f5c', hot2: '#f2793a', hotGlowRGB: '242,121,58',
    lossFill1: '#c94f4f', lossFill2: '#7a2e2e', lossGlow: 'rgba(248,113,113,0.7)', lossText: '#ffe8e8',
    countTrack: 'rgba(255,255,255,0.08)', countFill: '#e8eaed', ring: '#e8eaed',
    winFloat: '#e3b341', lossFloat: '#f87171',
    hover: 'rgba(76,139,245,0.75)', hoverFill: 'rgba(76,139,245,0.10)', hoverText: 'rgba(210,225,255,0.95)',
    reject: '#f87171', deadZone: 'rgba(18,20,23,0.55)', nowLine: 'rgba(140,150,165,0.3)',
    vigRGB: '76,139,245'
  },
  gold: {
    label: 'Gold Casino',
    css: { bg: '#0e0a04', panel: '#161006', border: '#3d3216', text: '#f4e9cf',
           dim: '#9a8c66', accent: '#d4af37', accentText: '#3a2c05',
           gain: '#9fe08a', loss: '#ff8ba0', win: '#ffe94a', toastBg: 'rgba(22,16,6,0.92)' },
    bg: '#0e0a04', gridLine: 'rgba(212,175,55,0.12)', gridLineMajor: 'rgba(212,175,55,0.20)',
    axisText: 'rgba(244,233,207,0.7)', multRGB: '224,193,110',
    line: '#f3d27a', lineGlow: 'rgba(243,210,122,0.85)', dot: '#ffffff',
    priceTagBg: '#b8860b', priceTagText: '#fff8e6',
    chip1: '#ffe082', chip2: '#d4af37', chipGlow: 'rgba(212,175,55,0.75)', betText: '#3a2c05',
    hot1: '#ffb35c', hot2: '#f2853a', hotGlowRGB: '255,160,70',
    lossFill1: '#b03a50', lossFill2: '#701c2c', lossGlow: 'rgba(240,70,100,0.9)', lossText: '#ffe3e8',
    countTrack: 'rgba(58,44,5,0.55)', countFill: '#fff4cc', ring: '#fff4cc',
    winFloat: '#ffe94a', lossFloat: '#ff6b81',
    hover: 'rgba(255,224,130,0.85)', hoverFill: 'rgba(255,224,130,0.10)', hoverText: 'rgba(255,244,204,0.95)',
    reject: '#f0506a', deadZone: 'rgba(14,10,4,0.55)', nowLine: 'rgba(243,210,122,0.35)',
    vigRGB: '255,215,90'
  },
  nova: {
    label: 'Futuristic',
    css: { bg: '#070714', panel: '#0d0d20', border: '#272750', text: '#eceafe',
           dim: '#8a87b0', accent: '#6a4cff', accentText: '#f2eeff',
           gain: '#7ae0c0', loss: '#ff8bb0', win: '#c9b8ff', toastBg: 'rgba(13,13,32,0.92)' },
    bg: '#070714', gridLine: 'rgba(122,120,255,0.12)', gridLineMajor: 'rgba(122,120,255,0.20)',
    axisText: 'rgba(206,204,255,0.7)', multRGB: '170,165,255',
    line: '#7aa8ff', lineGlow: 'rgba(122,168,255,0.85)', dot: '#ffffff',
    priceTagBg: '#6a4cff', priceTagText: '#f2eeff',
    chip1: '#a08bff', chip2: '#6a4cff', chipGlow: 'rgba(130,100,255,0.75)', betText: '#140a3a',
    hot1: '#ff7ae0', hot2: '#e04cff', hotGlowRGB: '230,90,255',
    lossFill1: '#d23a6a', lossFill2: '#801f44', lossGlow: 'rgba(255,70,130,0.9)', lossText: '#ffe3f0',
    countTrack: 'rgba(20,10,58,0.55)', countFill: '#efe9ff', ring: '#efe9ff',
    winFloat: '#c9b8ff', lossFloat: '#ff6b9d',
    hover: 'rgba(160,139,255,0.85)', hoverFill: 'rgba(160,139,255,0.10)', hoverText: 'rgba(226,218,255,0.95)',
    reject: '#ff5c8a', deadZone: 'rgba(7,7,20,0.55)', nowLine: 'rgba(122,168,255,0.35)',
    vigRGB: '160,139,255'
  }
};
var THEME_ORDER = ['rose', 'dark', 'neon', 'cyber', 'light', 'gold', 'nova'];

var COLOR = {}; // filled by applyTheme

function applyTheme(key) {
  var t = THEMES[key] || THEMES.rose;
  for (var k in t) if (k !== 'css' && k !== 'label') COLOR[k] = t[k];
  var r = document.documentElement.style;
  r.setProperty('--bg', t.css.bg);
  r.setProperty('--panel', t.css.panel);
  r.setProperty('--border', t.css.border);
  r.setProperty('--text', t.css.text);
  r.setProperty('--dim', t.css.dim);
  r.setProperty('--accent', t.css.accent);
  r.setProperty('--accent-text', t.css.accentText);
  r.setProperty('--gain', t.css.gain);
  r.setProperty('--loss', t.css.loss);
  r.setProperty('--win', t.css.win);
  r.setProperty('--toast-bg', t.css.toastBg);
}

export { THEMES, THEME_ORDER, COLOR, applyTheme };
