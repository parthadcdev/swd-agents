---
name: off
description: Turn off swd mode for this session, so requests are handled normally again. Use when the user runs /swd:off.
---

# swd mode off

The plugin's hook turns swd mode off when the user runs `/swd:off` or says
"stop swd".

Tell the user in one sentence that swd mode is off for this session and
that `/swd:build` still runs the team for a single requirement. If an swd
run is in progress, say so and ask whether to finish it or leave it to be
resumed later; do not abandon it silently.
