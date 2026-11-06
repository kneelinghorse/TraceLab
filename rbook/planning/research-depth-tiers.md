# Research Depth Tiers

DeepSearch uses a three-tier research depth system that balances thoroughness against cost and time. Each tier controls loop counts, source limits, convergence thresholds, and quality safeguards.

## Quick Reference

| Tier | Typical Duration | Sources Produced | Min Loops | Quality Gates | Extra Safeguards |
|------|------------------|-----------------|-----------|---------------|------------------|
| **Baseline** | 8-12 min | 50-60 | 2 | Standard | None |
| **Deep** | 20-25 min | 30-40 (vetted) | 5 | Stricter | None |
| **Alpha** | 1+ hour | ~20 (scrutinized) | 4 | Very strict (may reject) | Source diversity, contradiction detection |

---

## Tier Selection Criteria

### Baseline (Default)

The standard research tier. Produces thorough reports with 50-60 sources across multiple loops. Suitable for most research needs.

**Use when:**
- Any general research task (this is the default)
- Researching well-established or moderately complex domains
- You need a comprehensive report without extended wait times
- Good balance of thoroughness and turnaround

**Example scenarios:**
- "Compare PostgreSQL indexing strategies for time-series data"
- "What are the best practices for API rate limiting?"
- "Analyze authentication options for a microservices architecture"

**Observed behavior:**
- 8-12 minutes typical duration
- 50-60 sources across multiple loops
- Standard quality gates
- Convergence threshold: 0.05 (5% score delta)

---

### Deep

Higher-rigor research with 30-40 carefully vetted sources. Enforces stricter quality gates and runs a minimum of 5 loops.

**Use when:**
- You need higher confidence in the findings
- Strategic decisions requiring vetted sources
- Comparing multiple solutions where source quality matters
- Topics where you want fewer, more authoritative sources over volume

**Example scenarios:**
- "Compare PostgreSQL vs MongoDB for a time-series workload with production benchmarks"
- "Evaluate authentication strategies for regulated healthcare microservices"
- "Analyze tradeoffs between REST and GraphQL APIs with real-world case studies"

**Observed behavior:**
- 20-25 minutes typical duration
- 30-40 carefully vetted sources
- Stricter quality gates, minimum 5 loops
- Convergence threshold: 0.04 (4% score delta)
- Source quality floor: 0.6 (higher authority required)

---

### Alpha

Maximum-rigor research with ~20 highly scrutinized sources. Very strict quality gates that **may reject the research entirely** if the available evidence doesn't meet the bar. Not every topic is suitable for alpha.

**Use when:**
- Precision and source authority are critical
- The topic domain has sufficient high-quality sources to satisfy strict gates
- High-stakes decisions where you need maximum confidence
- Research where source quality is more important than source quantity

**Use with caution when:**
- The topic is niche or has sparse authoritative sources (alpha may reject)
- You need results quickly (1+ hour typical)
- Broad exploratory questions (alpha's strict gates may filter too aggressively)

**Example scenarios:**
- "Evaluate emerging consensus on AI agent architectures with peer-reviewed sources"
- "Analyze conflicting clinical studies on a specific treatment protocol"
- "Research regulatory compliance requirements for financial data handling"

**Observed behavior:**
- 1+ hour typical duration
- ~20 highly scrutinized sources
- Very strict quality gates (may reject research if evidence insufficient)
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

| Tier | Typical Duration | Sources Produced | Relative Cost |
|------|------------------|-----------------|---------------|
| Baseline | 8-12 minutes | 50-60 | 1x |
| Deep | 20-25 minutes | 30-40 (vetted) | 2-3x |
| Alpha | 1+ hour | ~20 (scrutinized) | 5-10x |

*Estimates based on observed production runs. Actual usage varies based on topic breadth, source availability, and quality gate outcomes. Alpha may take significantly longer or reject research entirely if domain sources are sparse.*

### When to Upgrade Tiers

**Baseline → Deep:**
- You need higher confidence in the findings
- Source quality matters more than source quantity
- Decision has meaningful consequences

**Deep → Alpha:**
- Sources conflict significantly and you need contradiction detection
- High-stakes decision requiring maximum source authority
- Topic has sufficient high-quality sources to pass strict gates

### When to Downgrade Tiers

**Alpha → Deep:**
- Topic lacks sufficient high-quality sources (alpha may reject)
- Time constraints — alpha takes 1+ hour vs 20-25 min
- Previous Alpha run rejected or showed diminishing returns

**Deep → Baseline:**
- Baseline already provides 50-60 sources — sufficient for most tasks
- Time-sensitive research where 8-12 min matters
- Following up on previous research

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
