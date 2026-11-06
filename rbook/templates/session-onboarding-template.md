# Onboarding Session Template

## Prerequisites
- [ ] Run: `./rbook/cli.py session onboard`
- [ ] Review output and note blockers, recent sessions, and active missions

## Session Start
```bash
./rbook/cli.py session start --type onboarding --title "Onboarding for [TASK]"
```

## Context to Capture
- [ ] Current sprint and focus
- [ ] Relevant decisions from recent sessions
- [ ] Active constraints or risks
- [ ] Immediate next planned work

## Suggested Captures
```bash
./rbook/cli.py session capture context "Key context item"
./rbook/cli.py session capture decision "Important decision"
./rbook/cli.py session capture constraint "Known constraint"
./rbook/cli.py session capture next-step "Immediate action"
```

## Session Completion
```bash
./rbook/cli.py session complete --summary "[AGENT] onboarded to [TASK]" \
  --next-steps "First action item" \
  --next-steps "Second action item"
```

Store the completed session ID in your handoff doc so the next agent can replay it with `./rbook/cli.py session show <ID>`.
