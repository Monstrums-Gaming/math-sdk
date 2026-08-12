// ---------------------------------------------------------------- debug helpers
// Pure helpers for the ?debug=1 harness: scenario parsing and the report
// summary. The harness itself (panel, placement, hooks) lives in main.js —
// these stay closure-free so they are unit-testable (debug.test.js).

// Scenario DSL — whitespace/comma-separated tokens, one per chip:
//   [col:]row[W|L]
//   col  = column index ahead of the first placeable column (default 0)
//   row  = signed cell-row offset from the current price row (+2 = two above)
//   W/L  = force this chip's outcome (omitted = normal random draw)
// Example: "0:+2W 0:0L 0:-2W" — a win-lose-win sandwich in one column.
// Returns [{col, row, force}] in token order (placement order = slot order).
function parseScenario(str) {
  var out = [];
  String(str || '').split(/[\s,;]+/).forEach(function (tok) {
    if (!tok) return;
    var m = /^(?:(\d+):)?([+-]?\d+)([WLwl])?$/.exec(tok);
    if (!m) return;
    out.push({
      col: m[1] ? parseInt(m[1], 10) : 0,
      row: parseInt(m[2], 10),
      force: m[3] ? m[3].toUpperCase() : null,
    });
  });
  return out;
}

// Roll the recorder's ring buffers up into the counters the panel shows.
function summarizeLog(log) {
  var reveals = log.reveals.length;
  var honest = log.reveals.filter(function (r) { return r.ok; }).length;
  return {
    reveals: reveals,
    honest: honest,
    violations: reveals - honest,
    teleports: log.teleports.length,
  };
}

// Steepest price slope ($/sim-s) over any `win`-sample window in a trace
// ([{t, p, m}]). Returns {slope, atT, phase, fromP, toP} or null.
function steepestSlope(trace, win) {
  win = win || 5;
  var worst = null;
  for (var i = win; i < trace.length; i++) {
    var a = trace[i - win], b = trace[i];
    var dt = b.t - a.t;
    if (dt <= 0) continue;
    var slope = Math.abs(b.p - a.p) / dt;
    if (!worst || slope > worst.slope) {
      worst = { slope: +slope.toFixed(2), atT: b.t, phase: b.m,
                fromP: +a.p.toFixed(3), toP: +b.p.toFixed(3) };
    }
  }
  return worst;
}

// Fold a trace into per-chip band entry/exit intervals + whether the line was
// inside the band at that chip's judgment. chips: [{t1,low,high}], reveals keyed
// by t1|low (a 2-bet chip is identified by its cell) give the judgment moment.
// Returns one row per chip.
function bandIntervals(trace, chips, reveals) {
  var judged = {};
  (reveals || []).forEach(function (r) { judged[r.t1 + '|' + r.low] = r; });
  return chips.map(function (c) {
    var enter = null, exit = null;
    for (var i = 0; i < trace.length; i++) {
      var inside = trace[i].p >= c.low && trace[i].p < c.high;
      if (inside && enter === null) enter = trace[i].t;
      if (inside) exit = trace[i].t;
    }
    var rev = judged[c.t1 + '|' + c.low];
    return {
      t1: c.t1, band: [c.low, c.high],
      enter: enter, exit: exit,
      insideAtResolve: rev ? (rev.price >= c.low && rev.price < c.high) : null,
      won: rev ? rev.won : null,
    };
  });
}

// An incident is a trace whose steepest slope exceeds `limit` $/sim-s.
function detectIncident(trace, limit, win) {
  var s = steepestSlope(trace, win);
  return s && s.slope >= limit ? s : null;
}

export { parseScenario, summarizeLog, steepestSlope, bandIntervals, detectIncident };
