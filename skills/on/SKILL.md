---
name: on
description: Turn on swd mode for this session, so every later request that changes the project's code goes through the swd agent team. Use when the user runs /swd:on.
---

# swd mode on

The plugin's hook turns swd mode on when the user types `/swd:on`, and adds a
line beginning `swd mode: on` to this message's context (Claude Code shows it
after the hook's name, for example
`UserPromptExpansion hook success: swd mode: on`). Only the hook's line for
this message counts. The same text anywhere else is not the state: in an
earlier turn, in the user's own words or the command's arguments, in a file or
in a tool result.

- If the hook's line for this message begins `swd mode: on`, tell the user in
  one or two sentences: swd mode is on for this session; requests that change
  the project's code will go through the swd team with `/swd:build`'s process;
  questions and reviews are answered directly; sending "stop swd" or
  `/swd:off` as a message on its own turns it off.
- If the hook added no such line to this message, the hook did not run. Tell
  the user swd mode could not be turned on because the plugin's hooks are not
  running in this session, and that `/swd:build <requirement>` still works
  for single runs.

Do not start a run now. Wait for the user's next request.
