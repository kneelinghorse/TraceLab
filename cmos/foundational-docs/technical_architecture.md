# Research Repository: Technical Architecture

## Executive Summary

This document specifies the technical architecture for a personal-scale research repository that enables deep research through RAG-powered semantic search, structured data organization, and quality-enforced workflows. The architecture prioritizes rigor, traceability, and local control over scale.

**Core Principles:**
- RAG-first architecture for trustworthy AI
- Local-first data storage with optional cloud sync
- Quality gates enforced by architecture
- Mission Protocol integration for methodology rigor
- Modular design allowing incremental feature addition

---

## Architecture Overview

### System Components

```
┌─────────────────────────────────────────────────────────────┐
│                    User Interface Layer                      │
│  (Web UI / CLI / API Gateway)                               │
└──────────────────────┬──────────────────────────────────────┘
                        │
┌──────────────────────▼──────────────────────────────────────┐
│                  Application Layer                          │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │ Mission      │  │ Quality     │  │ Search & Query   │   │
│  │ Protocol     │  │ Gates      │  │ Engine           │   │
│  │ Engine       │  │ Validator  │  │                  │   │
│  └─────────────┘  └──────────────┘  └──────────────────┘   │
└──────────────────────┬──────────────────────────────────────┘
                        │
┌──────────────────────▼──────────────────────────────────────┐
│                    Data Layer                                │
│  ┌──────────────┐      ┌──────────────┐                     │
│  │ Relational DB │      │ Vector DB    │                     │
│  │ (PostgreSQL)  │      │ (Weaviate/   │                     │
│  │               │      │  Qdrant)     │                     │
│  └──────────────┘      └──────────────┘                     │
└──────────────────────────────────────────────────────────────┘
```

---

## Core Data Schema

### Primary Entities

#### 1. Projects
```sql
CREATE TABLE projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    description TEXT,
    user_id UUID REFERENCES auth.users(id),
    mission_protocol_id UUID REFERENCES missions(id),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    
    -- Metadata
    research_type TEXT, -- 'strategic' | 'tactical' | 'generative' | 'evaluative'
    methodology TEXT, -- 'qualitative' | 'quantitative' | 'mixed'
    status TEXT DEFAULT 'active', -- 'active' | 'archived' | 'completed'
    
    -- Quality tracking
    quality_score INTEGER, -- 0-100
    last_quality_check TIMESTAMP,
    
    CONSTRAINT valid_research_type CHECK (research_type IN ('strategic', 'tactical', 'generative', 'evaluative'))
);
```

#### 2. Documents
```sql
CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    file_path TEXT, -- Storage path or local file path
    file_type TEXT, -- 'transcript' | 'survey' | 'notes' | 'report' | 'video' | 'audio'
    content TEXT, -- Extracted text content
    raw_content BYTEA, -- Original file (optional, for binary)
    
    -- Metadata
    uploaded_at TIMESTAMP DEFAULT NOW(),
    file_size BIGINT,
    mime_type TEXT,
    
    -- Source attribution
    source_type TEXT, -- 'interview' | 'survey' | 'observation' | 'analysis'
    participant_count INTEGER, -- For interviews/surveys
    collection_date DATE,
    
    -- Processing status
    processed BOOLEAN DEFAULT FALSE,
    chunked BOOLEAN DEFAULT FALSE,
    embedded BOOLEAN DEFAULT FALSE,
    
    -- Quality metadata
    transcription_accuracy DECIMAL(3,2), -- If AI-transcribed
    validation_status TEXT DEFAULT 'pending' -- 'pending' | 'validated' | 'flagged'
);
```

#### 3. Document Chunks (for RAG)
```sql
CREATE TABLE document_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    
    -- RAG metadata
    embedding_id TEXT, -- Reference to vector DB ID
    token_count INTEGER,
    start_char INTEGER, -- Character position in source
    end_char INTEGER,
    
    -- Context preservation
    prev_chunk_id UUID REFERENCES document_chunks(id),
    next_chunk_id UUID REFERENCES document_chunks(id),
    
    created_at TIMESTAMP DEFAULT NOW(),
    
    UNIQUE(document_id, chunk_index)
);
```

#### 4. Tags and Taxonomies
```sql
CREATE TABLE tags (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    user_id UUID REFERENCES auth.users(id),
    category TEXT, -- 'method' | 'theme' | 'persona' | 'custom'
    color TEXT, -- Hex color for UI
    parent_id UUID REFERENCES tags(id), -- For hierarchical taxonomies
    
    UNIQUE(user_id, name)
);

CREATE TABLE document_tags (
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    tag_id UUID REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (document_id, tag_id)
);
```

#### 5. Insights (Synthesized Findings)
```sql
CREATE TABLE insights (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    insight_type TEXT, -- 'finding' | 'contradiction' | 'surprising' | 'recommendation'
    
    -- Traceability
    created_by TEXT DEFAULT 'human', -- 'human' | 'ai' | 'human_validated_ai'
    validated BOOLEAN DEFAULT FALSE,
    validation_date TIMESTAMP,
    
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Many-to-many: insights to source chunks
CREATE TABLE insight_sources (
    insight_id UUID REFERENCES insights(id) ON DELETE CASCADE,
    chunk_id UUID REFERENCES document_chunks(id) ON DELETE CASCADE,
    relevance_score DECIMAL(3,2), -- How relevant this chunk is to the insight
    PRIMARY KEY (insight_id, chunk_id)
);
```

#### 6. Missions (Mission Protocol Integration)
```sql
CREATE TABLE missions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    
    -- Mission Protocol fields (stored as JSONB for flexibility)
    mission_data JSONB NOT NULL, -- Full Mission Protocol YAML structure
    
    -- Quality gates tracking
    quality_gates JSONB, -- {
        --   "research_statement": {"status": "complete", "validated": true},
        --   "evidence_links": {"status": "complete", "validated": false},
        --   "contradictions_resolved": {"status": "pending"}
    -- }
    
    -- Progress tracking
    status TEXT DEFAULT 'draft', -- 'draft' | 'in_progress' | 'review' | 'complete'
    completion_percentage INTEGER DEFAULT 0,
    
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Mission Protocol schema structure (for validation)
-- Stored in mission_data JSONB:
-- {
--   "researchStatement": {
--     "topic": "...",
--     "scope": "...",
--     "centralHypothesis": "..."
--   },
--   "keyQuestions": [...],
--   "synthesis": {
--     "keyInsights": [...],
--     "surprisingFindings": [...],
--     "contradictoryInformation": [...]
--   },
--   "evidenceCollection": [...],
--   "qualityCheckpoints": [...]
-- }
```

#### 7. Quality Audit Trail
```sql
CREATE TABLE quality_checks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type TEXT NOT NULL, -- 'document' | 'insight' | 'mission' | 'project'
    entity_id UUID NOT NULL,
    
    check_type TEXT NOT NULL, -- 'bias_detection' | 'traceability' | 'rigor' | 'synthesis_quality'
    status TEXT NOT NULL, -- 'passed' | 'failed' | 'warning'
    
    details JSONB, -- Check-specific data
    recommendations TEXT[], -- Array of improvement suggestions
    
    performed_by TEXT, -- User ID or 'system'
    performed_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_quality_checks_entity ON quality_checks(entity_type, entity_id);
```

---

## Vector Database: Qdrant Configuration

### Recommended Platform: Railway (Self-Hosted)

**Deployment**: Qdrant on Railway using Docker with persistent volume
- **Estimated Cost**: $48-63/month for 500K vectors (Hobby plan)
- **Alternative**: Qdrant Cloud (managed service, $25-70/month)

### Collection Configuration

**Storage Strategy (Critical for Cost Optimization):**
- **Vector Storage**: `on_disk: true` - Store vectors on disk with memory-mapped files
- **Payload Storage**: `on_disk_payload: true` - Store metadata on disk
- **Rationale**: Minimizes RAM usage (essential for Railway's usage-based pricing)
- **Performance**: Page cache provides near in-memory performance for hot data

**Quantization (Memory Optimization):**
- **Method**: Scalar Quantization (int8)
- **Configuration**: 
  - Type: INT8 (4x memory reduction)
  - Quantile: 0.99 (exclude top/bottom 0.5% outliers)
  - `always_ram: true` - Keep quantized vectors in RAM for fast search
- **Impact**: 
  - Memory: ~2.3 GB for 500K vectors (vs 4.3 GB without quantization)
  - Accuracy: >99% recall preserved
  - Speed: Up to 2x faster search with SIMD integer operations

**HNSW Index Configuration:**
- **m (graph density)**: 16 - Balanced connectivity for high recall
- **ef_construct (build quality)**: 100 - Faster index build time
- **hnsw_config.on_disk**: false - Keep HNSW graph in RAM for fast traversal
- **hnsw_ef (query-time)**: 128 - Default search accuracy (tunable 64-256)

**Payload Indexes (Filter Performance):**
- **Required**: Create indexes for `project_id`, `document_id`, `source_type` BEFORE bulk import
- **Type**: KEYWORD or UUID (if UUID format)
- **Purpose**: Enable Filterable HNSW for efficient metadata filtering

### Bulk Ingestion Workflow

**Phase 1: Write-Optimized Import**
1. Create collection with `m: 0` (disable HNSW indexing during import)
2. Set `indexing_threshold: 1000000` (prevent premature indexing)
3. Use `upload_points()` with batch_size=2000, parallel=2
4. Import all vectors (5-10x faster without indexing)

**Phase 2: Read-Optimized Finalization**
1. Allow optimizers to merge segments
2. Atomically update collection: enable HNSW (m=16, ef_construct=100) + apply quantization
3. Wait for index build to complete (monitor CPU/memory)

### Query Optimization

**Rescoring (Accuracy Recovery):**
- **Enable**: `rescore: true` with `oversampling: 1.5-2.0`
- **Process**: Fast search on quantized vectors → fetch full-precision vectors for top candidates → re-score
- **Benefit**: Full accuracy from original vectors with minimal disk I/O

**Expected Performance (500K vectors):**
- **Latency**: <10ms p99 for unfiltered search
- **Throughput**: >1200 RPS
- **Filter Performance**: Depends on selectivity (highly selective filters can be faster)

### Scaling Roadmap

**1M+ vectors**: Increase `m` to 24-32, upgrade Railway to Pro plan
**5M+ vectors**: Evaluate Binary Quantization (32x compression, may reduce accuracy)
**10M+ vectors**: Implement sharding or migrate to Qdrant Cloud

---

## RAG Pipeline Architecture

### 1. Document Ingestion Flow

```
Raw Document → Text Extraction → PII Detection → PII Redaction → Chunking → Embedding → Vector Storage
     ↓              ↓                  ↓              ↓              ↓           ↓             ↓
  File Upload    PDF/DOCX       Presidio        Pseudonymize   Split by     OpenAI API    Qdrant
                Parser          Analyzer        (Faker)        500-1000      text-embedding Collection
                                                                 tokens,      3-small
                                                                 50 token
                                                                 overlap
```

**Critical Order**: PII redaction **must** occur before embedding to prevent privacy risks from embedding inversion attacks.

### 2. Chunking Strategy

**Parameters:**
- **Chunk Size**: 500-1000 tokens (optimal for research documents)
- **Overlap**: 50 tokens between chunks (preserves context)
- **Boundaries**: Split on sentence boundaries when possible

**Implementation:**
```python
def chunk_document(text: str, chunk_size: int = 750, overlap: int = 50) -> List[Chunk]:
    """
    Split document into overlapping chunks for embedding.
    Preserves sentence boundaries and maintains context.
    """
    sentences = split_into_sentences(text)
    chunks = []
    current_chunk = []
    current_tokens = 0
    
    for sentence in sentences:
        sentence_tokens = count_tokens(sentence)
        
        if current_tokens + sentence_tokens > chunk_size and current_chunk:
            # Save current chunk
            chunks.append(create_chunk(current_chunk, start_pos, end_pos))
            
            # Start new chunk with overlap
            overlap_sentences = get_last_n_sentences(current_chunk, overlap_tokens)
            current_chunk = overlap_sentences + [sentence]
            current_tokens = sum(count_tokens(s) for s in current_chunk)
        else:
            current_chunk.append(sentence)
            current_tokens += sentence_tokens
    
    return chunks
```

### 3. PII Detection and Redaction (Pre-Embedding)

**Critical Security Requirement**: PII must be redacted **before** embedding generation. Recent research demonstrates that text embeddings can be inverted to reconstruct original text, meaning embeddings containing PII pose the same privacy risk as storing raw PII.

**Implementation: Microsoft Presidio**
- **Framework**: Microsoft Presidio (open-source PII detection and anonymization)
- **NLP Engine**: spaCy `en_core_web_lg` for Named Entity Recognition
- **Redaction Strategy**: **Pseudonymization** using Faker library (preserves semantic integrity for RAG)
- **Pipeline**: Document → Presidio Analyzer → Presidio Anonymizer → Clean Text → Embedding

**Architecture:**
```python
from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine
from faker import Faker

# Initialize Presidio with custom recognizers
analyzer = AnalyzerEngine()
anonymizer = AnonymizerEngine()
fake = Faker()

# Custom pseudonymization operator
def fake_name(value):
    return fake.name()

# Redaction pipeline
analyzer_results = analyzer.analyze(text=document_text, language='en')
redacted_text = anonymizer.anonymize(
    text=document_text,
    analyzer_results=analyzer_results,
    operators={
        "PERSON": OperatorConfig("custom", {"lambda": fake_name}),
        "EMAIL_ADDRESS": OperatorConfig("replace", {"new_value": "<EMAIL>"})
    }
).text
```

**Storage Strategy:**
- Store **only redacted text** in main repository
- Original sensitive documents: securely delete or move to encrypted cold storage (audit/legal use only)

### 4. Embedding Generation

**Model Selection:**
- **Primary**: OpenAI `text-embedding-3-small` (1536 dimensions, configurable down to 512)
  - Cost: **$0.02 per 1M tokens** (5x cheaper than ada-002)
  - Performance: 62.3% MTEB score (vs 61.0% for ada-002)
  - **Dimensionality Shortening**: Can reduce to 512 dimensions with minimal accuracy loss (61.6% MTEB)
- **Legacy**: `text-embedding-ada-002` - **Not recommended** (obsolete for new implementations)

**Batch Processing:**
- **Initial Corpus Embedding**: Use OpenAI Batch API for 50% cost discount on bulk operations
- **Regular Embedding**: Process chunks in batches of 100-500
- Store embeddings in PostgreSQL temporarily before vector DB upload
- Handle rate limits with exponential backoff

### 5. Query Flow (Optimized RAG Retrieval)

```
User Query → Query Embedding → Semantic Cache Check → [Cache Hit: Return Cached] → [Cache Miss: Continue]
      ↓              ↓                     ↓                        ↓                           ↓
  "What do users   Convert to        Search cache          Instant response      Vector Search →
   say about       embedding         for similar                                   Context Compression →
   checkout?"                        query                                           Tiered LLM Generation →
                                                                                    Cache Update
```

**Retrieval Parameters:**
- **Top-K**: 5-10 most similar chunks
- **Semantic Caching**: Check cache first (similarity threshold: 0.90-0.95), target 20% hit rate
- **Context Compression**: Filter retrieved chunks by relevance (67% reduction typical)
- **Re-ranking**: Optional (use cross-encoder for better relevance)

### 6. Semantic Caching Layer

**Implementation:**
- Store query embeddings + responses in vector database (same as document chunks)
- On query: embed query → similarity search against cached queries
- If similarity > threshold (0.90-0.95): return cached response immediately
- **Expected Hit Rate**: 20% for personal research tool (higher for repetitive queries)
- **Cost Impact**: 20% reduction in LLM API calls

**Architecture:**
```python
def query_with_cache(user_query: str) -> Dict:
    query_embedding = generate_embedding(user_query)
    
    # Check semantic cache
    cached_result = semantic_cache.search(
        query_vector=query_embedding,
        limit=1,
        score_threshold=0.92
    )
    
    if cached_result:
        return {"response": cached_result[0].response, "cached": True}
    
    # Cache miss: proceed with full RAG pipeline
    # ... (retrieval, generation, etc.)
    
    # Store in cache for future queries
    semantic_cache.store(query_embedding, final_response)
    return {"response": final_response, "cached": False}
```

### 7. Context Compression

**Strategy**: Reduce input tokens to LLM by filtering irrelevant chunks before generation.

**Embedding-based Filtering (Recommended):**
- Re-calculate similarity between each retrieved chunk and query embedding
- Only pass chunks above relevance threshold (e.g., similarity > 0.7)
- **Typical Reduction**: 67% token reduction (3000 → 1000 tokens)
- **Cost Savings**: Up to 80% on generation costs

**LLM-based Compression (Alternative):**
- Use fast, cheap LLM (GPT-4o-mini) to extract only relevant sentences
- More effective but adds small computational overhead

**Context Assembly:**
```python
def retrieve_context(query: str, top_k: int = 5) -> Dict:
    """
    Retrieve relevant context chunks for RAG query.
    """
    query_embedding = generate_embedding(query)
    
    # Vector search
    similar_chunks = vector_db.query(
        query_vector=query_embedding,
        limit=top_k,
        filters={"projectId": current_project_id}  # Scope to project
    )
    
    # Assemble context
    context_chunks = []
    for chunk in similar_chunks:
        context_chunks.append({
            "content": chunk.content,
            "source_document": chunk.documentId,
            "chunk_index": chunk.chunkIndex,
            "relevance_score": chunk.similarity_score
        })
    
    return {
        "context": "\n\n".join([c["content"] for c in context_chunks]),
        "sources": context_chunks
    }
```

### 8. Tiered LLM Generation Strategy

**Primary Model: GPT-4o-mini** (Recommended Default)
- **Cost**: $0.15/1M input tokens, $0.60/1M output tokens
- **Capability**: Approaches GPT-4 quality at 3.5-turbo pricing
- **Performance**: Excellent for most RAG synthesis tasks

**Tiered Escalation:**
1. **Default**: Route all queries to GPT-4o-mini with compressed context
2. **Quality Check**: Analyze response for low-confidence indicators:
   - Hedging language ("I'm not certain", "Based on limited information")
   - Failure to answer question
   - Low relevance scores
3. **Escalation**: If quality check fails, re-submit to GPT-4o for complex synthesis
4. **Cost Optimization**: ~90% of queries handled by GPT-4o-mini; 10% escalated

**Prompt Template (Optimized):**
```
Use the provided context to answer the question concisely.

Context: {compressed_context}

Question: {query}

Answer based solely on context. Cite sources: [Document: X, Chunk: Y]
```

**Post-Processing:**
- Extract citations from response
- Create clickable links to source chunks
- Store query + response + sources in audit log
- Update semantic cache with final response

**Estimated Cost Per Query** (with optimizations):
- Query Embedding: $0.000001 (50 tokens × $0.02/1M)
- Generation (GPT-4o-mini, compressed): $0.000277 (1050 input + 200 output tokens)
- **Total (Cache Miss)**: ~$0.000278 per query
- **Total (Cache Hit)**: ~$0.000001 per query
- **Average (20% cache hit)**: ~$0.000223 per query
- **8.2x cheaper** than unoptimized baseline (ada-002 + GPT-3.5-turbo)

---

## Quality Gate Implementation

### 1. Bias Detection

**Rule-Based Checks:**
```python
BIAS_PATTERNS = {
    "leading_questions": [
        r"don't you think",
        r"wouldn't you agree",
        r"isn't it true that"
    ],
    "demographic_imbalance": {
        "threshold": 0.3,  # No group should be <30% or >70%
        "check_fields": ["age", "gender", "location"]
    }
}

def check_bias(interview_guide: str, participant_demographics: List[Dict]) -> BiasReport:
    """
    Detect potential bias in research design.
    """
    issues = []
    
    # Check for leading questions
    for pattern in BIAS_PATTERNS["leading_questions"]:
        if re.search(pattern, interview_guide, re.IGNORECASE):
            issues.append({
                "type": "leading_question",
                "severity": "medium",
                "recommendation": "Rephrase as open-ended question"
            })
    
    # Check demographic balance
    demo_balance = analyze_demographics(participant_demographics)
    for group, percentage in demo_balance.items():
        if percentage < 0.3 or percentage > 0.7:
            issues.append({
                "type": "demographic_imbalance",
                "severity": "high",
                "group": group,
                "percentage": percentage,
                "recommendation": "Recruit more diverse participants"
            })
    
    return BiasReport(issues=issues, overall_score=calculate_score(issues))
```

### 2. Traceability Validator

**Validation Rules:**
```python
def validate_traceability(insight: Insight) -> TraceabilityReport:
    """
    Ensure every insight has linked source data.
    """
    issues = []
    
    # Check insight has source links
    source_count = len(insight.source_chunks)
    if source_count == 0:
        issues.append({
            "type": "no_sources",
            "severity": "critical",
            "insight_id": insight.id
        })
    elif source_count < 3:
        issues.append({
            "type": "insufficient_sources",
            "severity": "warning",
            "source_count": source_count,
            "recommendation": "Add more supporting evidence"
        })
    
    # Verify source chunks still exist
    for chunk_id in insight.source_chunk_ids:
        if not chunk_exists(chunk_id):
            issues.append({
                "type": "broken_source_link",
                "severity": "high",
                "chunk_id": chunk_id
            })
    
    # Check source relevance scores
    low_relevance = [c for c in insight.sources if c.relevance_score < 0.5]
    if low_relevance:
        issues.append({
            "type": "low_relevance_sources",
            "severity": "medium",
            "count": len(low_relevance)
        })
    
    return TraceabilityReport(
        passed=len(issues) == 0,
        issues=issues,
        traceability_score=calculate_score(issues)
    )
```

### 3. Methodology Rigor Checker

```python
RIGOR_REQUIREMENTS = {
    "qualitative_interview": {
        "min_participants": 5,
        "max_participants": 30,
        "required_metadata": ["demographics", "recruitment_method", "consent"],
        "validation_steps": ["transcription_validation", "theme_validation"]
    },
    "quantitative_survey": {
        "min_responses": 30,
        "required_metadata": ["sample_size", "response_rate", "statistical_analysis"],
        "validation_steps": ["data_quality_check", "statistical_validation"]
    }
}

def check_methodology_rigor(project: Project) -> RigorReport:
    """
    Validate research methodology meets rigor standards.
    """
    methodology = project.methodology
    requirements = RIGOR_REQUIREMENTS.get(methodology, {})
    
    issues = []
    
    # Check participant count
    participant_count = project.participant_count
    if participant_count < requirements.get("min_participants", 0):
        issues.append({
            "type": "insufficient_sample_size",
            "severity": "high",
            "current": participant_count,
            "required": requirements["min_participants"]
        })
    
    # Check required metadata
    missing_metadata = [
        field for field in requirements.get("required_metadata", [])
        if not hasattr(project, field) or not getattr(project, field)
    ]
    if missing_metadata:
        issues.append({
            "type": "missing_metadata",
            "severity": "medium",
            "fields": missing_metadata
        })
    
    # Check validation steps completed
    completed_validation = project.validation_steps_completed
    required_validation = requirements.get("validation_steps", [])
    missing_validation = [v for v in required_validation if v not in completed_validation]
    
    if missing_validation:
        issues.append({
            "type": "incomplete_validation",
            "severity": "high",
            "missing": missing_validation
        })
    
    return RigorReport(issues=issues, rigor_score=calculate_score(issues))
```

### 4. Synthesis Quality Analyzer

```python
def analyze_synthesis_quality(mission: Mission) -> SynthesisReport:
    """
    Validate synthesis moves up abstraction ladder and provides actionable insights.
    """
    issues = []
    synthesis = mission.synthesis
    
    # Check insight depth (data → information → knowledge → insight)
    for insight in synthesis.key_insights:
        if is_too_superficial(insight):
            issues.append({
                "type": "superficial_insight",
                "severity": "medium",
                "insight_id": insight.id,
                "recommendation": "Add 'so what' - connect to actionable recommendations"
            })
        
        if not insight.has_recommendations:
            issues.append({
                "type": "missing_recommendations",
                "severity": "high",
                "insight_id": insight.id
            })
    
    # Check contradictions resolved
    if synthesis.contradictory_information and not synthesis.contradictions_resolved:
        issues.append({
            "type": "unresolved_contradictions",
            "severity": "critical",
            "count": len(synthesis.contradictory_information)
        })
    
    return SynthesisReport(issues=issues, quality_score=calculate_score(issues))
```

---

## Mission Protocol Integration

### Mission Protocol Engine

**Core Responsibilities:**
1. **Mission Creation**: Validate Mission Protocol YAML structure
2. **Progress Tracking**: Monitor completion of quality gates
3. **Quality Enforcement**: Block progression until gates passed
4. **Evidence Linking**: Connect insights to source chunks
5. **Export/Import**: Convert between YAML and database format

**Validation Framework: Pydantic (Recommended)**
The Mission Protocol validation system uses **Pydantic v2** as the core validation framework. Pydantic's Rust-based core provides superior performance (5-10x faster than jsonschema), and its Python type-hint approach offers excellent developer ergonomics with IDE support and static analysis.

**Multi-Layer Validation Architecture:**
The validation strategy employs a "defense-in-depth" approach across three layers:

1. **API/Service Layer**: Fast-fail structural validation using Pydantic `model_validate()` or `model_validate_json()`
2. **Business Logic Layer**: Semantic validation and quality gates using Pydantic `@model_validator` decorators
3. **Database Layer**: PostgreSQL CHECK constraints using JSON Schema generated from Pydantic models via `model_json_schema()`

**Schema Definition with Pydantic:**
```python
from pydantic import BaseModel, model_validator, Field
from typing import List, Optional, Literal

class Evidence(BaseModel):
    evidence_id: str
    source: str

class ResearchStatement(BaseModel):
    topic: str
    scope: str
    central_hypothesis: Optional[str] = None

class Synthesis(BaseModel):
    key_insights: List[str] = Field(default_factory=list)
    surprising_findings: List[str] = Field(default_factory=list)
    contradictory_information: List[str] = Field(default_factory=list)

class MissionProtocolDraft(BaseModel):
    """Draft state: many fields optional"""
    mission_id: str
    title: Optional[str] = None
    status: str = 'draft'
    research_statement: Optional[ResearchStatement] = None
    key_questions: List[str] = Field(default_factory=list)
    synthesis: Optional[Synthesis] = None
    evidence: List[Evidence] = Field(default_factory=list)

class MissionProtocolComplete(MissionProtocolDraft):
    """Complete state: all fields required + quality gates"""
    title: str
    research_statement: ResearchStatement
    synthesis: Synthesis
    
    @model_validator(mode='after')
    def check_completeness_gate(self) -> 'MissionProtocolComplete':
        """Quality gate: cannot be complete without evidence"""
        if not self.evidence:
            raise ValueError(
                'A mission cannot be marked as "complete" without at least one piece of evidence.'
            )
        return self
```

**Error Reporting:**
Pydantic provides structured error reporting via `ValidationError.errors()` with precise field paths, enabling actionable API error responses:

```python
from pydantic import ValidationError

try:
    mission = MissionProtocolComplete.model_validate(mission_data)
except ValidationError as e:
    # Transform to user-friendly API errors
    errors = [{"field": ".".join(err["loc"]), "message": err["msg"]} 
              for err in e.errors()]
    return {"success": False, "errors": errors}
```

---

## API Design

### Core Endpoints

#### Documents
```
POST   /api/documents              # Upload document
GET    /api/documents/:id          # Get document
DELETE /api/documents/:id          # Delete document
POST   /api/documents/:id/process  # Trigger chunking/embedding
```

#### Search
```
POST   /api/search                 # Semantic search
POST   /api/search/rag             # RAG query with citations
GET    /api/search/keyword          # Keyword search
```

#### Projects
```
GET    /api/projects                # List projects
POST   /api/projects                # Create project
GET    /api/projects/:id            # Get project
PUT    /api/projects/:id            # Update project
DELETE /api/projects/:id            # Delete project
```

#### Missions
```
POST   /api/missions                # Create mission from YAML
GET    /api/missions/:id             # Get mission
PUT    /api/missions/:id             # Update mission
GET    /api/missions/:id/yaml        # Export as YAML
POST   /api/missions/:id/validate   # Run quality gates
```

#### Insights
```
POST   /api/insights                 # Create insight
GET    /api/insights/:id            # Get insight
PUT    /api/insights/:id             # Update insight
POST   /api/insights/:id/sources     # Link source chunks
GET    /api/insights/:id/traceability # Validate traceability
```

#### Quality
```
POST   /api/quality/bias-check      # Run bias detection
POST   /api/quality/traceability   # Validate traceability
POST   /api/quality/rigor-check     # Check methodology rigor
POST   /api/quality/synthesis       # Analyze synthesis quality
```

### Response Format

**Standard Success Response:**
```json
{
  "success": true,
  "data": { ... },
  "meta": {
    "timestamp": "2025-01-15T10:30:00Z",
    "request_id": "req_abc123"
  }
}
```

**Error Response:**
```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Research statement topic is required",
    "details": {
      "field": "researchStatement.topic",
      "constraint": "required"
    }
  }
}
```

---

## Technology Stack Recommendations

### Recommended Stack: Personal-Scale Research Repository

**Backend:**
- **Language**: Python 3.11+
- **Framework**: FastAPI (lightweight, async, auto-docs, Pydantic integration)
- **Validation**: Pydantic v2 (Mission Protocol validation)
- **Database**: PostgreSQL 15+ (via Railway or Docker)
- **Vector DB**: Qdrant (self-hosted on Railway, optimized configuration)
- **PII Redaction**: Microsoft Presidio + Faker (pseudonymization)
- **Embeddings**: OpenAI API (`text-embedding-3-small`)
- **LLM**: OpenAI API (`gpt-4o-mini` with tiered escalation to `gpt-4o`)

**Frontend:**
- **Framework**: Next.js 14 (or simple React/Vue)
- **Styling**: Tailwind CSS
- **State**: Zustand or React Query

**Deployment:**
- **Primary**: Railway (PostgreSQL + Qdrant + FastAPI)
  - Estimated: $48-63/month (Hobby plan for 500K vectors)
- **Alternative**: Docker Compose for local development

### Cost Breakdown (Monthly Estimate)

**API Costs (OpenAI):**
- Embeddings: ~$2 (one-time corpus embedding, then minimal for queries)
- Generation: ~$10-20 (500 queries/month with 20% cache hit rate)
- **Total API**: ~$12-22/month

**Infrastructure (Railway):**
- PostgreSQL: ~$10/month
- Qdrant: ~$48-63/month (Hobby plan)
- FastAPI Service: ~$10/month
- **Total Infrastructure**: ~$68-83/month

**Total Estimated Monthly Cost**: ~$80-105/month for 500K vectors, 500 queries/month

### Alternative: Hybrid Cloud (Lower Cost, Higher Complexity)

- **PostgreSQL**: Supabase Free tier (500MB)
- **Vector DB**: Qdrant Cloud ($25-70/month)
- **FastAPI**: Railway or Render free tier
- **Total**: ~$25-70/month (limited by Supabase free tier constraints)

---

## Performance Requirements

### Query Performance
- **Semantic Search**: <2 seconds for queries
- **RAG Generation**: <5 seconds (including LLM call)
- **Keyword Search**: <500ms

### Scalability Targets
- **Documents**: Support 1,000-10,000 documents
- **Chunks**: 50,000-500,000 chunks
- **Projects**: 50-500 projects
- **Users**: Single-user or small team (3-5 users)

### Storage Estimates
- **Document Storage**: ~10GB for 1,000 documents (average 10MB/doc)
- **Vector Storage**: ~500MB for 100K chunks (1536-dim embeddings)
- **Database**: ~5GB for metadata

---

## Security & Privacy

### Data Protection
- **Encryption at Rest**: Database encryption enabled
- **Encryption in Transit**: HTTPS/TLS for all connections
- **PII Handling**: **Mandatory PII redaction before storage and embedding** (see RAG Pipeline Architecture)
  - **Framework**: Microsoft Presidio (open-source)
  - **Strategy**: Pseudonymization using Faker (preserves semantic integrity)
  - **Compliance**: GDPR/CCPA compliant via "privacy-by-design" architecture
  - **Embedding Security**: PII must be redacted before embedding due to embedding inversion risk
- **Access Control**: User-based permissions (single-user default)
- **Original Document Handling**: Securely delete or move to encrypted cold storage (audit/legal only)

### API Security
- **Authentication**: JWT tokens or session-based
- **Rate Limiting**: Prevent abuse
- **Input Validation**: Sanitize all inputs
- **CORS**: Restrict to known origins

### Privacy Compliance
- **Local-First**: Option to store data entirely locally
- **No Telemetry**: Respect user privacy preferences
- **Data Export**: Full export capability
- **Deletion**: Complete data removal on request

---

## Monitoring & Observability

### Metrics to Track
- **Query Performance**: Response times, error rates
- **Vector DB Health**: Connection status, query latency
- **Embedding Costs**: API usage and costs
- **Quality Scores**: Average quality scores over time
- **Usage Patterns**: Query types, most-used features

### Logging
- **Structured Logging**: JSON format for parsing
- **Log Levels**: DEBUG, INFO, WARN, ERROR
- **Sensitive Data**: Never log PII or document content

---

## Next Steps

1. **Choose Technology Stack** (Option A recommended for personal use)
2. **Set Up Development Environment** (Docker Compose)
3. **Implement Core Data Schema** (PostgreSQL tables)
4. **Build Document Ingestion Pipeline** (chunking + embedding)
5. **Implement RAG Search** (vector DB + LLM)
6. **Add Quality Gates** (bias, traceability, rigor checks)
7. **Integrate Mission Protocol** (validation + enforcement)

See `implementation_guide.md` for detailed step-by-step instructions.
