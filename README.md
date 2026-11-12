# swd-agents

A Claude Code plugin. A principal software engineer agent takes a requirement,
gets one approval from you on the spec and plan, then runs a team of
specialist agents until the work is built, tested and committed on a branch.

## Requirements

- Claude Code
- Python 3 (standard library only), for the run checker
- git

## Use

Load the plugin for a session:

```bash
claude --plugin-dir /path/to/swd-agents
```

Then, in the project you want work done in:

```
/swd:build <your requirement>
```

## Develop

```bash
python3 -m unittest discover -s tests -v
claude plugin validate .
```

The design is in `docs/superpowers/specs/2026-11-12-swd-agents-design.md`.
