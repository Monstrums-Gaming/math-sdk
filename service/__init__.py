"""Mystery-box build service — a thin HTTP API around the dynamic generator.

Wraps ``games/mystery_box_dynamic`` so a backoffice can create a mystery box, trigger a
build, and download the ACP publish files. The math engine is untouched; each build shells
out to the same ``run.py`` a manual ``build.sh`` invocation uses.
"""
