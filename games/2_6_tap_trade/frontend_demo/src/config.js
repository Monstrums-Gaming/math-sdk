// ---------------------------------------------------------------- config

var CFG = {
  startPrice: 2993.0,
  tick: 0.1,
  timeScale: 1.3,        // sim-time speed multiplier — 1.3 = whole game runs 30% faster
  velDamping: 1.4,
  velNoise: 1.1,
  meanRevert: 0.10,
  anchorVol: 0.25,

  cellSeconds: 5,
  cellDollars: 0.5,
  pxPerSec: 14,
  pxPerDollar: 110,
  nowFrac: 0.4,

  minLeadSec: 2.5,       // chip must start at least this far in the future
  guideLeadSec: 6,       // steering ramps in this long before the chip's column
  resolveSec: 1.6,       // reveal window: a chip resolves within this many seconds
                         // of its column reaching the now-line (the cell stays a
                         // full grid cell wide — only the resolution moment is
                         // early, so chips never drift into the history zone)
  houseEdge: 0.035,      // display pricing only — true odds come from the ladder modes
  betSizes: [1, 2, 5, 20],  // quick chips — a subset of betLevels
  // The offered bet grid (mirrors the production Stake bet menu), clamped to
  // [minBet, maxBet]. LOCAL uses it as-is; LIVE rebuilds it from the RGS
  // config.betLevels. Everything not on a quick chip goes in the "+" menu.
  betLevels: [1, 1.4, 2, 5, 7, 8, 14, 20, 40, 50, 100, 150, 200, 400, 500, 1000],
  minBet: 1,             // hard floor on any offered bet
  maxBet: 1000,          // hard cap on any offered bet
  startBalance: 2000,
  historySeconds: 140    // covers the visible past even at the 0.5x zoom floor
};

var MONO = 'ui-monospace,"SF Mono",Menlo,Consolas,monospace';

export { CFG, MONO };
