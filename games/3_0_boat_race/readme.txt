Boat Race (3_0_boat_race)
=========================

Pick 1 of 4 boats, watch a certified pre-generated race, get paid by the picked
boat's finishing place: 3.00x / 0.60x / 0.20x / 0 for 1st/2nd/3rd/4th at exactly
1/4 each. RTP 0.95, payout std 1.2031, hit rate 75%. One mode `race`, cost 1.0.

Books are PICK-NEUTRAL: the transcript addresses racers r0..r3 where r0 is always
the player's pick; the client maps the chosen boat onto r0 at render time, so all
four boats have identical odds by construction and one 4,000-book pool serves
every pick. Each book certifies a 30-row rank timeline (adjacent-swap overtakes
only, converging on the finishing order) that the frontend race is obliged to
land on exactly.

Build:
    make run GAME=3_0_boat_race                       # dev (readable books)
    COMPRESSION=1 RUN_FORMAT_CHECKS=1 \
        env/bin/python games/3_0_boat_race/run.py     # production publish set

Verify (mandatory before upload — execute_all_tests only proves book<->LUT):
    env/bin/python games/3_0_boat_race/verify_books.py

Frontend demo bundle (samples published books, 10 per place):
    env/bin/python games/3_0_boat_race/frontend_demo/build_demo_data.py [dest]

The playable frontend lives outside this repo at stake-engine/monstrums/html/
(standalone Three.js, mock RGS + rank-director certified replay).
