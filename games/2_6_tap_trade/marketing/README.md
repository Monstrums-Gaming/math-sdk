# Tap Trade — Stake Engine tile art

`foreground.png` + `background.png` are the two 1254×1254 images the Stake Engine
Publish page takes (same spec as the previously published mystery-box thumbnail).
The tile template puts the **Key Focus Area in the upper band** and overlays the
game title + "MONSTRUMS" across the lower half, so both images keep all art in
the top ~57% and contain **no title lettering**:

- `foreground.png` — transparent emblem (tap ring, hand cursor, market line +
  arrow, candlesticks) rendered from `foreground.svg`; fully transparent below
  57% of the tile.
- `background.png` — the game's chart scene (lit teal gradient, cell grid,
  glowing rising line with area fill and the live dot, faint multiplier labels),
  falling to a quiet dark lower half for the title overlay. Mean luminance is
  kept ~20% (52/255): the platform's brightness check auto-lightens anything
  darker, so keep any re-render at or above this level.

Re-render: serve this folder over HTTP and screenshot `foreground.svg` in a
1254×1254 page (`omitBackground` for the transparency); the background is a
one-shot canvas drawing — both scripts live in the session history / can be
recreated from this description at any size.
