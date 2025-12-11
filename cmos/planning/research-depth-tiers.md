# Research Depth Tiers

DeepSearch uses a three-tier research depth system that balances thoroughness against cost and time. Each tier controls loop counts, source limits, convergence thresholds, and quality safeguards.

## Quick Reference

| Tier | Max Loops | Min Loops | Max Sources | Convergence Threshold | Quality Floor | Extra Safeguards |
|------|-----------|-----------|-------------|----------------------|---------------|------------------|
| **Baseline** | 3 | 2 | 15 | 0.05 | 0.5 | None |
| **Deep** | 5 | 3 | 20 | 0.04 | 0.6 | None |
| **Alpha** | 6 | 4 | 25 | 0.03 | 0.7 | Source diversity, contradiction detection |

---

## Tier Selection Criteria

### Baseline (Default)

**Use when:**
- Quick verification of known facts
- Researching well-established domains
- Routine questions with expected answers
- Time-sensitive queries where speed matters
- Low-stakes decisions

**Example scenarios:**
- "What are the system requirements for PostgreSQL 16?"
- "How do I configure nginx reverse proxy?"
- "What's the current version of React?"

**Configuration:**
- 2-3 research loops
- Up to 15 sources
- Convergence threshold: 0.05 (5% score delta)
- Source quality floor: 0.5 (medium authority)

---

### Deep

**Use when:**
- Strategic decisions requiring comprehensive analysis
- Comparing multiple solutions or approaches
- Technical architecture research
- Market or competitive analysis
- Decisions with moderate risk

**Example scenarios:**
- "Compare PostgreSQL vs MongoDB for a time-series workload"
- "What authentication strategies work best for microservices?"
- "Analyze the tradeoffs between REST and GraphQL APIs"

**Configuration:**
- 3-5 research loops
- Up to 20 sources
- Convergence threshold: 0.04 (4% score delta)
- Source quality floor: 0.6 (higher authority required)

---

### Alpha

**Use when:**
- Novel domains with limited prior research
- Conflicting or contradictory sources expected
- Foundational research for critical decisions
- High-stakes decisions requiring maximum confidence
- Research where source quality is paramount

**Example scenarios:**
- "Evaluate emerging consensus on AI agent architectures"
- "Research cutting-edge approaches to federated learning"
- "Analyze conflicting studies on database performance claims"

**Configuration:**
- 4-6 research loops
- Up to 25 sources
- Convergence threshold: 0.03 (3% score delta)
- Source quality floor: 0.7 (high authority required)

**Alpha-only safeguards:**
- **Source diversity enforcement**: Requires minimum 4 unique domains
- **Contradiction detection**: Identifies and reports conflicting claims
- **Late-stage consensus optimization**: Reduces reflection runs after loop 4

---

## Setting Research Depth

### Option 1: YAML Mission File

Use the `researchDepth` field (or aliases: `research_depth`, `depth`):

```yaml
# Using researchDepth (preferred)
missionId: "RESEARCH.001"
title: "PostgreSQL vs MongoDB Analysis"
objective: "Compare database options for time-series data"
successCriteria:
  - "Identify performance characteristics of each"
  - "Analyze cost implications"
  - "Recommend optimal choice with rationale"
researchDepth: "deep"
```

```yaml
# Using depth alias (also valid)
missionId: "RESEARCH.002"
title: "Emerging AI Agent Patterns"
objective: "Research novel approaches to AI agent orchestration"
successCriteria:
  - "Survey current state of the art"
  - "Identify consensus and conflicting views"
depth: "alpha"
```

**Metadata fallback** (if top-level field not set):

```yaml
missionId: "RESEARCH.003"
title: "Quick API Reference"
objective: "Verify current API rate limits"
successCriteria:
  - "Document rate limit values"
metadata:
  research_depth: "baseline"
  tags: ["reference", "quick-lookup"]
```

---

### Option 2: TraceLab Mission (PostgreSQL)

When creating missions via TraceLab, set depth in the `research_phases` JSONB column:

```json
{
  "mission_id": "TL-2024-001",
  "title": "Competitive Analysis",
  "objective": "Analyze competitor pricing strategies",
  "success_criteria": [
    "Document pricing tiers for top 5 competitors",
    "Identify market positioning patterns"
  ],
  "research_phases": {
    "depth": "deep",
    "max_loops": 5,
    "deliverable_format": "markdown"
  }
}
```

**Field priority for TraceLab rows:**
1. `research_phases.depth` (highest priority)
2. `research_phases.research_depth`
3. `research_phases.researchDepth`
4. `context.depth`
5. `context.research_depth`
6. Default: `baseline`

---

### Option 3: Programmatic API

When initializing state directly in Python:

```python
from deepsearch.agent.state import empty_state
from deepsearch.agent.depth import ResearchDepth

# Using enum (type-safe)
state = empty_state(
    mission_id="API-001",
    mission_objectives=["Analyze authentication options"],
    research_depth=ResearchDepth.DEEP,
)

# Using string (also valid)
state = empty_state(
    mission_id="API-002",
    mission_objectives=["Quick fact verification"],
    research_depth="baseline",
)

# Alpha tier with full configuration
state = empty_state(
    mission_id="API-003",
    mission_objectives=[
        "Survey emerging consensus on topic",
        "Identify contradictory claims",
    ],
    research_depth=ResearchDepth.ALPHA,
    project_id="my-project-uuid",
)
```

**Overriding depth-derived values:**

```python
# Use deep tier but increase max loops
state = empty_state(
    mission_id="API-004",
    mission_objectives=["Extended analysis"],
    research_depth=ResearchDepth.DEEP,
    max_loops=7,  # Override deep tier default of 5
    min_loops=4,  # Override deep tier default of 3
)
```

---

## Cost and Time Tradeoffs

### Estimated Resource Usage

| Tier | Typical Duration | API Calls | Token Usage | Relative Cost |
|------|------------------|-----------|-------------|---------------|
| Baseline | 2-4 minutes | 6-10 | 15-25K | 1x |
| Deep | 5-10 minutes | 12-18 | 30-50K | 2-3x |
| Alpha | 8-15 minutes | 18-25 | 50-80K | 3-5x |

*Estimates assume standard mission complexity. Actual usage varies based on topic breadth and source availability.*

### When to Upgrade Tiers

**Baseline → Deep:**
- Initial research returns conflicting information
- Coverage scores plateau below 0.8
- Decision requires comparing multiple options

**Deep → Alpha:**
- Sources conflict significantly
- Novel domain with sparse authoritative sources
- Foundational research for critical architecture decisions

### When to Downgrade Tiers

**Alpha → Deep:**
- Well-established topic with clear consensus
- Time constraints require faster results
- Previous Alpha run showed no contradictions

**Deep → Baseline:**
- Simple fact verification
- Following up on previous comprehensive research
- Reference lookups (versions, configurations, etc.)

---

## Troubleshooting Convergence Failures

### Symptoms

**Early termination without convergence:**
```
termination_reason: "max_loops_reached"
convergence_history: [0.45, 0.52, 0.58, 0.62, 0.65]
```

**Oscillating scores:**
```
convergence_history: [0.55, 0.62, 0.58, 0.64, 0.60]
```

### Common Causes and Solutions

#### 1. Tier too shallow for topic complexity

**Problem:** Baseline tier on a complex topic
```yaml
researchDepth: "baseline"
objective: "Compare 10 different cloud providers"  # Too broad
```

**Solution:** Upgrade to Deep or Alpha
```yaml
researchDepth: "deep"
objective: "Compare 10 different cloud providers"
```

#### 2. Overly broad objectives

**Problem:** Mission tries to cover too much ground
```yaml
successCriteria:
  - "Analyze all aspects of microservices"
  - "Compare every database option"
  - "Document complete history of the technology"
```

**Solution:** Narrow scope or split into multiple missions
```yaml
successCriteria:
  - "Identify top 3 database options for the use case"
  - "Compare performance characteristics"
  - "Recommend one with rationale"
```

#### 3. Source quality issues

**Problem:** Low-quality sources pass quality floor
```
sources_found: [
  {"authority_score": 0.51, ...},  # Barely passes baseline floor
  {"authority_score": 0.48, ...},  # Should be filtered
]
```

**Solution:** Use higher tier with stricter quality floor
```yaml
researchDepth: "alpha"  # Quality floor: 0.7
```

#### 4. Conflicting sources without detection

**Problem:** Sources contradict but aren't flagged (Baseline/Deep)
```
findings: [
  "Source A claims X is best",
  "Source B claims Y is best",
]
```

**Solution:** Enable Alpha tier for contradiction detection
```yaml
researchDepth: "alpha"
# Alpha enables: enable_contradiction_detection: true
```

### Debugging Commands

**Check current depth configuration:**
```python
from deepsearch.agent.depth import get_depth_config, ResearchDepth

config = get_depth_config(ResearchDepth.ALPHA)
print(f"Max loops: {config.max_loops}")
print(f"Quality floor: {config.source_quality_floor}")
print(f"Contradiction detection: {config.enable_contradiction_detection}")
```

**Inspect state after research:**
```python
# After research completes
print(f"Depth: {state['research_depth']}")
print(f"Loops completed: {state['research_loop_count']}")
print(f"Convergence history: {state['convergence_history']}")
print(f"Termination reason: {state['termination_reason']}")

# Alpha-only: check contradiction report
if state.get('contradiction_report'):
    print(f"Contradictions found: {state['contradiction_report']}")
```

### Recovery Strategies

1. **Restart with higher tier:**
   - If baseline fails → try deep
   - If deep fails → try alpha

2. **Narrow scope and retry:**
   - Split broad mission into focused sub-missions
   - Each sub-mission can use appropriate tier

3. **Manual loop override:**
   ```python
   # Force more loops on difficult topic
   state = empty_state(
       mission_id="RETRY-001",
       research_depth=ResearchDepth.DEEP,
       max_loops=8,  # Override default
   )
   ```

4. **Review and supplement:**
   - Export partial results
   - Create follow-up mission targeting gaps

---

## Configuration Reference

### DepthConfig Fields

| Field | Type | Description |
|-------|------|-------------|
| `max_loops` | int | Maximum research-reflection loops |
| `min_loops` | int | Minimum loops before convergence exit |
| `max_sources` | int | Maximum total sources to collect |
| `sources_per_loop` | int | Target sources per loop |
| `convergence_threshold` | float | Score delta for convergence detection |
| `convergence_window` | int | Loops to check for stability |
| `source_quality_floor` | float | Minimum source authority (0.0-1.0) |
| `require_source_diversity` | bool | Enforce domain diversity |
| `min_unique_domains` | int | Minimum unique domains required |
| `enable_contradiction_detection` | bool | Detect conflicting claims |
| `consensus_runs` | int | Reflection runs for confidence |
| `consensus_runs_late_stage` | int\|None | Reduced runs after min_loops |

### Full Tier Configurations

```python
# Baseline defaults
BASELINE = DepthConfig(
    max_loops=3,
    min_loops=2,
    max_sources=15,
    sources_per_loop=5,
    convergence_threshold=0.05,
    convergence_window=3,
    source_quality_floor=0.5,
    require_source_diversity=False,
    enable_contradiction_detection=False,
    consensus_runs=5,
)

# Deep defaults
DEEP = DepthConfig(
    max_loops=5,
    min_loops=3,
    max_sources=20,
    sources_per_loop=5,
    convergence_threshold=0.04,
    convergence_window=3,
    source_quality_floor=0.6,
    require_source_diversity=False,
    enable_contradiction_detection=False,
    consensus_runs=5,
)

# Alpha defaults
ALPHA = DepthConfig(
    max_loops=6,
    min_loops=4,
    max_sources=25,
    sources_per_loop=5,
    convergence_threshold=0.03,
    convergence_window=4,
    source_quality_floor=0.7,
    require_source_diversity=True,
    min_unique_domains=4,
    enable_contradiction_detection=True,
    consensus_runs=5,
    consensus_runs_late_stage=3,
)
```

---

## Related Documentation

- [Technical Architecture](technical_architecture.md) - System design overview
- [Deployment Guide](deployment.md) - Running DeepSearch in production
- [Prompt Engineering](prompt_engineering.md) - Tuning research prompts
