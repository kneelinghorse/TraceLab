# [Your Project Name]

**Status**: [In Development / Beta / Production]  
**Managed with**: CMOS (Context + Mission Orchestration System)

[Brief 2-3 sentence description of what your project does and why it exists]

---

## Quick Start

```bash
# Install dependencies
[your install command]

# Setup environment
[your setup commands]

# Run development server
[your dev command]

# Run tests
[your test command]
```

---

## Project Documentation

- **Roadmap**: See `docs/roadmap.md` for project vision and sprint plan
- **Technical Architecture**: See `docs/technical_architecture.md` for system design
- **API Documentation**: [Link to your API docs if applicable]

---

## Development

### Prerequisites
- [Language] [version]
- [Database] [version]
- [Other dependencies]

### Environment Setup
```bash
# [Step-by-step setup instructions]
```

### Running Tests
```bash
# [Your test commands]
```

### Building for Production
```bash
# [Your build commands]
```

---

## Project Management with CMOS

This project uses CMOS for mission-based development workflow.

**For contributors**:
- Mission tracking: See `rbook/missions/backlog.yaml`
- Project history: Stored in `rbook/db/rbook.sqlite`
- Session logs: See `rbook/SESSIONS.jsonl`

**For AI agents**:
- Application code guidance: See `agents.md` (this project root)
- CMOS operations guidance: See `rbook/agents.md`
- Build session prompts: See `rbook/docs/build-session-prompt.md`

**CMOS commands** (from project root):
```bash
# View current mission status
./rbook/cli.py db show current

# View sprint progress
./rbook/cli.py db show backlog

# Validate system integrity
./rbook/cli.py validate health
```

---

## Contributing

[Your contribution guidelines]

---

## License

[Your license]

---

## CMOS Directory

The `rbook/` directory contains project management infrastructure:
- Mission and sprint tracking
- Context and session history
- Planning and orchestration scripts

**Do not write application code in `rbook/`** - it's for project management only.

See `rbook/README.md` for CMOS-specific documentation.

