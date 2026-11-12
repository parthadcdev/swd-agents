---
name: on
description: Turn on swd mode for this session, so every later request that changes the project's code goes through the swd agent team. Use when the user runs /swd:on.
---

# swd mode on

The plugin's hook turns swd mode on when the user runs `/swd:on`, and adds a
line beginning `swd mode: on` to this message's context.

- If you can see that line, tell the user in one or two sentences: swd mode
  is on for this session; requests that change the project's code will go
  through the swd team with `/swd:build`'s process; questions and reviews
  are answered directly; "stop swd" or `/swd:off` turns it off.
- If you cannot see that line, the hook did not run. Tell the user swd mode
  could not be turned on because the plugin's hooks are not running in this
  session, and that `/swd:build <requirement>` still works for single runs.

Do not start a run now. Wait for the user's next request.
