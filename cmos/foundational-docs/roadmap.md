# Research Repository: Development Roadmap

## Executive Summary

This roadmap outlines the development plan for building a personal-scale research repository with RAG-powered semantic search, Mission Protocol integration, and privacy-compliant data processing. The architecture prioritizes rigor, traceability, local control, and cost-effectiveness.

**Key Technical Foundations:**
- Pydantic-based Mission Protocol validation
- Microsoft Presidio for PII redaction (pre-embedding)
- Optimized RAG pipeline (text-embedding-3-small, GPT-4o-mini)
- Qdrant on Railway with scalar quantization
- Semantic caching and context compression

**Target Scale:**
- 50,000 - 500,000 document chunks
- 500 queries/month
- Estimated cost: $80-105/month

---

## Phase 1: Foundation & Core Infrastructure (Weeks 1-4)

### Week 1: Project Setup & Database Schema

**Goal:** Establish development environment and core data structures

**Technical Milestones:**
- [ ] Initialize FastAPI project structure
- [ ] Set up PostgreSQL database (local Docker)
- [ ] Implement core schema migrations:
  - Projects, Documents, Document Chunks
  - Tags and Taxonomies
  - Insights with source linking
  - Missions (JSONB storage)
  - Quality audit trail
- [ ] Set up Alembic for migrations
- [ ] Create initial Pydantic models for database entities

**Key Decisions:**
- PostgreSQL 15+ with JSONB for Mission Protocol storage
- FastAPI with Pydantic v2 for validation
- SQLAlchemy ORM for database operations

**Success Criteria:**
- Database schema deployed and tested
- Can create/read/update projects and documents
- Mission Protocol JSONB column supports nested structures

### Week 2: PII Redaction Pipeline

**Goal:** Implement privacy-compliant document processing

**Technical Milestones:**
- [ ] Install and configure Microsoft Presidio
  - Presidio Analyzer with spaCy `en_core_web_lg`
  - Presidio Anonymizer with Faker integration
- [ ] Create custom recognizers for research domain
- [ ] Implement PII redaction service
  - Document input → PII detection → Pseudonymization → Clean output
- [ ] Integrate redaction into document ingestion flow
- [ ] Set up secure storage for original documents (optional)

**Key Decisions:**
- Pseudonymization over label replacement (preserves semantic integrity)
- Custom recognizers for domain-specific PII patterns
- Original documents: secure deletion (or encrypted cold storage)

**Success Criteria:**
- PII detection accuracy >95% on sample research documents
- Redacted documents preserve semantic meaning
- Redaction completes in <5 seconds per document

### Week 3: Document Processing & Chunking

**Goal:** Build document ingestion pipeline with text extraction and chunking

**Technical Milestones:**
- [ ] Implement document parsers:
  - PDF (PyPDF2 or pdfplumber)
  - DOCX (python-docx)
  - Plain text
- [ ] Create chunking service:
  - Sentence-aware splitting
  - 500-1000 token chunks
  - 50 token overlap
- [ ] Implement document upload API endpoint
- [ ] Add processing status tracking
- [ ] Create background job queue for async processing

**Key Decisions:**
- Token-based chunking (using tiktoken for accuracy)
- Overlap strategy to preserve context

**Success Criteria:**
- Can upload PDF, DOCX, and TXT files
- Documents chunked correctly with metadata preserved
- Processing pipeline handles errors gracefully

### Week 4: Embedding Generation & Storage

**Goal:** Generate embeddings and store in Qdrant

**Technical Milestones:**
- [ ] Set up OpenAI API integration
- [ ] Implement embedding generation service:
  - Use `text-embedding-3-small` (1536 dim, optionally reduced to 512)
  - Batch processing for corpus embedding
  - Use Batch API for initial corpus (50% discount)
- [ ] Set up Qdrant on Railway (or local Docker)
- [ ] Configure Qdrant collection:
  - on_disk: true (vectors and payloads)
  - Payload indexes for project_id, document_id, source_type
- [ ] Implement vector upload service
- [ ] Create ingestion workflow: chunk → embed → store

**Key Decisions:**
- OpenAI `text-embedding-3-small` (not ada-002)
- Qdrant on Railway for production
- Dimensionality: start with 1536, test 512 for cost savings

**Success Criteria:**
- Can embed document chunks and store in Qdrant
- Collection configured with optimal settings
- Bulk ingestion of 100K+ chunks completes successfully

---

## Phase 2: RAG Search & Query (Weeks 5-8)

### Week 5: Basic RAG Implementation

**Goal:** Build core RAG query functionality

**Technical Milestones:**
- [ ] Implement query embedding generation
- [ ] Create vector search service:
  - Query Qdrant with metadata filters
  - Retrieve top-k chunks
  - Apply project_id/document_id filtering
- [ ] Integrate GPT-4o-mini for answer generation
- [ ] Build basic RAG prompt template
- [ ] Implement citation extraction and formatting
- [ ] Create search API endpoint

**Key Decisions:**
- GPT-4o-mini as primary model (not GPT-3.5-turbo)
- Top-k retrieval: 5-10 chunks
- Citation format: [Document: X, Chunk: Y]

**Success Criteria:**
- Can perform semantic search and get relevant results
- Generated answers include accurate citations
- Query latency <5 seconds end-to-end

### Week 6: Context Compression & Optimization

**Goal:** Optimize RAG pipeline for cost and performance

**Technical Milestones:**
- [ ] Implement embedding-based context filtering:
  - Re-score retrieved chunks against query
  - Filter by relevance threshold (0.7+)
  - Reduce context from 3000 → 1000 tokens
- [ ] Add semantic caching layer:
  - Store query embeddings + responses in Qdrant
  - Similarity search for cache hits (threshold 0.90-0.95)
  - Return cached responses when found
- [ ] Implement cache management (TTL, size limits)
- [ ] Measure and optimize cache hit rate (target 20%)

**Key Decisions:**
- Embedding-based filtering (faster than LLM compression)
- Cache in same Qdrant instance (separate collection)

**Success Criteria:**
- Context compression reduces tokens by 60-70%
- Semantic cache achieves 15-20% hit rate
- Query costs reduced by 80% vs baseline

### Week 7: Tiered LLM Strategy

**Goal:** Implement intelligent model routing

**Technical Milestones:**
- [ ] Build quality assessment service:
  - Detect hedging language
  - Check answer completeness
  - Validate citation quality
- [ ] Implement tiered routing:
  - Default: GPT-4o-mini
  - Escalation: GPT-4o on quality failure
- [ ] Add logging for escalation events
- [ ] Monitor escalation rate (target <10%)
- [ ] Create cost tracking dashboard

**Key Decisions:**
- Quality heuristics over confidence scores (simpler, effective)
- Escalation only on clear failures

**Success Criteria:**
- 90%+ of queries handled by GPT-4o-mini
- Escalated queries receive better answers
- Average cost per query <$0.0003

### Week 8: Qdrant Optimization & Bulk Import

**Goal:** Optimize Qdrant for production scale

**Technical Milestones:**
- [ ] Implement optimized bulk import workflow:
  - Create collection with m=0 (no indexing during import)
  - Set indexing_threshold: 1000000
  - Use upload_points() with batch_size=2000
- [ ] Apply post-import optimization:
  - Enable HNSW (m=16, ef_construct=100)
  - Apply scalar quantization (int8, always_ram: true)
  - Configure rescoring (oversampling: 1.5-2.0)
- [ ] Performance testing:
  - Query latency benchmarks
  - Memory usage validation
  - Cost verification on Railway

**Key Decisions:**
- Two-phase import (write-optimized → read-optimized)
- Scalar quantization for memory efficiency

**Success Criteria:**
- Bulk import of 500K vectors completes in <2 hours
- Query latency <10ms p99
- Memory usage <2.5 GB for 500K vectors

---

## Phase 3: Mission Protocol Integration (Weeks 9-12)

### Week 9: Pydantic Validation Framework

**Goal:** Implement Mission Protocol validation with Pydantic

**Technical Milestones:**
- [ ] Define Pydantic models for Mission Protocol:
  - MissionProtocolDraft (optional fields)
  - MissionProtocolComplete (required + quality gates)
  - Nested models: ResearchStatement, Synthesis, Evidence
- [ ] Implement multi-layer validation:
  - API layer: Fast-fail structural validation
  - Business layer: @model_validator for quality gates
  - Database layer: JSON Schema CHECK constraints
- [ ] Create error transformation service (Pydantic → API errors)
- [ ] Build validation API endpoints

**Key Decisions:**
- Pydantic v2 (not jsonschema)
- Separate models for draft vs complete states
- Quality gates implemented as validators

**Success Criteria:**
- Mission Protocol YAML validated at API layer
- Quality gates block invalid state transitions
- Error messages are actionable and specific

### Week 10: Mission Protocol Engine

**Goal:** Build core Mission Protocol management system

**Technical Milestones:**
- [ ] Implement Mission Protocol CRUD operations
- [ ] Create YAML import/export functionality
- [ ] Build progress tracking:
  - Completion percentage calculation
  - Quality gate status
  - Validation status (draft/valid/invalid)
- [ ] Implement evidence linking:
  - Connect insights to source chunks
  - Track relevance scores
  - Validate links on completion
- [ ] Create Mission Protocol API endpoints

**Key Decisions:**
- Store full Mission Protocol as JSONB in PostgreSQL
- Track validation_status in separate column
- Evidence links stored in insight_sources table

**Success Criteria:**
- Can create, read, update Mission Protocols
- YAML import/export works correctly
- Evidence linking connects insights to document chunks

### Week 11: Quality Gates Implementation

**Goal:** Enforce research quality standards

**Technical Milestones:**
- [ ] Implement quality gate validators:
  - Research statement completeness
  - Evidence links required for insights
  - Contradictions must be resolved
  - Synthesis must have key insights
- [ ] Create quality gate status API
- [ ] Build quality checkpoint UI/API
- [ ] Implement blocking logic (prevent completion without gates)
- [ ] Add quality score calculation

**Key Decisions:**
- Quality gates as Pydantic validators (not separate rules engine)
- Blocking vs non-blocking gates (configurable)

**Success Criteria:**
- Quality gates block invalid completions
- Status API shows which gates are passed/failed
- Quality scores reflect gate compliance

### Week 12: Mission Protocol UI Integration

**Goal:** Connect Mission Protocol to user interface

**Technical Milestones:**
- [ ] Create Mission Protocol creation form
- [ ] Build progress visualization
- [ ] Implement quality gate indicators
- [ ] Add evidence linking interface
- [ ] Create Mission Protocol list/view pages

**Key Decisions:**
- UI framework: Next.js 14 with React
- Form library: React Hook Form with Pydantic validation

**Success Criteria:**
- Users can create and edit Mission Protocols
- Progress and quality gates visible in UI
- Evidence linking works from UI

---

## Phase 4: Quality Assurance & Advanced Features (Weeks 13-16)

### Week 13: Quality Gate Automation

**Goal:** Automate bias detection and traceability checks

**Technical Milestones:**
- [ ] Implement bias detection service:
  - Leading question detection
  - Demographic imbalance checks
  - Rule-based pattern matching
- [ ] Build traceability validator:
  - Check insight-source links
  - Validate source relevance scores
  - Detect broken links
- [ ] Create methodology rigor checker
- [ ] Implement synthesis quality analyzer
- [ ] Add automated quality checks API

**Key Decisions:**
- Rule-based checks for performance
- Store quality check results in audit trail

**Success Criteria:**
- Bias detection identifies common issues
- Traceability validator ensures all insights have sources
- Quality checks run automatically on document update

### Week 14: Performance Optimization

**Goal:** Optimize system performance and costs

**Technical Milestones:**
- [ ] Implement query result caching
- [ ] Optimize database queries (indexes, N+1 fixes)
- [ ] Profile and optimize embedding generation
- [ ] Tune Qdrant parameters (hnsw_ef, quantization)
- [ ] Monitor and optimize API costs:
  - Track OpenAI usage
  - Optimize prompt tokens
  - Measure cache effectiveness

**Key Decisions:**
- Redis for query result caching (optional)
- Monitoring via Prometheus/Grafana or Railway metrics

**Success Criteria:**
- Query latency <2 seconds (95th percentile)
- API costs within budget ($80-105/month)
- System handles 100 concurrent queries

### Week 15: Advanced Search Features

**Goal:** Enhance search capabilities

**Technical Milestones:**
- [ ] Implement hybrid search (semantic + keyword)
- [ ] Add faceted search (filter by source type, date, tags)
- [ ] Build query refinement UI
- [ ] Implement search history
- [ ] Create saved searches feature

**Key Decisions:**
- Keyword search using PostgreSQL full-text search
- Combine with semantic search via weighted scoring

**Success Criteria:**
- Users can combine semantic and keyword search
- Faceted filters work efficiently
- Search results are relevant and fast

### Week 16: Testing & Documentation

**Goal:** Comprehensive testing and documentation

**Technical Milestones:**
- [ ] Write unit tests for core services:
  - PII redaction accuracy
  - Embedding generation
  - Mission Protocol validation
- [ ] Create integration tests:
  - End-to-end document ingestion
  - RAG query pipeline
  - Mission Protocol workflow
- [ ] Performance testing:
  - Load testing (500 concurrent queries)
  - Stress testing (1M+ vectors)
- [ ] Write API documentation (OpenAPI/Swagger)
- [ ] Create user documentation:
  - Getting started guide
  - Mission Protocol tutorial
  - Best practices

**Key Decisions:**
- pytest for Python testing
- Locust for load testing
- FastAPI auto-generated docs

**Success Criteria:**
- Test coverage >80%
- Documentation complete and clear
- System handles target load

---

## Phase 5: Production Readiness (Weeks 17-20)

### Week 17: Deployment & Infrastructure

**Goal:** Deploy to production on Railway

**Technical Milestones:**
- [ ] Set up Railway services:
  - PostgreSQL database
  - Qdrant vector database
  - FastAPI application
- [ ] Configure environment variables
- [ ] Set up database backups
- [ ] Implement health checks
- [ ] Configure monitoring and alerting

**Key Decisions:**
- Railway for all services (simplicity)
- Automated backups via Railway or manual scripts

**Success Criteria:**
- All services deployed and running
- Health checks passing
- Backups configured

### Week 18: Security Hardening

**Goal:** Secure the application for production

**Technical Milestones:**
- [ ] Implement authentication (JWT or session-based)
- [ ] Add rate limiting
- [ ] Configure CORS properly
- [ ] Enable HTTPS/TLS
- [ ] Security audit:
  - Input validation review
  - SQL injection prevention
  - XSS protection
- [ ] Set up secure document storage

**Key Decisions:**
- JWT tokens for API authentication
- Rate limiting via FastAPI middleware

**Success Criteria:**
- Authentication working
- No security vulnerabilities
- All data encrypted in transit

### Week 19: Monitoring & Observability

**Goal:** Comprehensive monitoring and logging

**Technical Milestones:**
- [ ] Set up application logging (structured JSON)
- [ ] Configure error tracking (Sentry or similar)
- [ ] Implement metrics collection:
  - Query performance
  - API costs
  - Quality scores
  - System health
- [ ] Create monitoring dashboard
- [ ] Set up alerting for critical issues

**Key Decisions:**
- Structured logging (JSON format)
- Railway metrics + custom dashboards

**Success Criteria:**
- All critical metrics tracked
- Alerts configured for failures
- Dashboard shows system health

### Week 20: Launch & Iteration

**Goal:** Launch MVP and gather feedback

**Technical Milestones:**
- [ ] Load test production environment
- [ ] Fix any performance bottlenecks
- [ ] Create user onboarding flow
- [ ] Deploy to production
- [ ] Monitor initial usage
- [ ] Collect user feedback
- [ ] Plan next iteration

**Key Decisions:**
- Soft launch with limited users
- Iterative improvement based on feedback

**Success Criteria:**
- System stable in production
- Users can successfully use core features
- Feedback collected for improvements

---

## Success Metrics

### Technical Metrics
- **Query Performance**: <2 seconds (95th percentile)
- **Cost Efficiency**: <$0.0003 average cost per query
- **PII Detection**: >95% accuracy (precision + recall)
- **Cache Hit Rate**: 15-20%
- **System Uptime**: >99.5%

### Feature Completion
- [ ] Document ingestion with PII redaction
- [ ] RAG-powered semantic search
- [ ] Mission Protocol integration
- [ ] Quality gates enforcement
- [ ] Cost-optimized architecture

### User Experience
- [ ] Can upload and search research documents
- [ ] Mission Protocols enforce research rigor
- [ ] Quality gates provide clear feedback
- [ ] Search results are relevant and cited

---

## Risk Mitigation

### Technical Risks
- **Qdrant performance**: Optimize configuration, monitor closely, have scaling plan
- **API costs**: Implement caching aggressively, monitor usage, set budgets
- **PII detection accuracy**: Continuous evaluation, custom recognizers, manual review process
- **Embedding inversion**: Redaction before embedding (already architecture)

### Operational Risks
- **Railway costs**: Monitor usage, optimize resource allocation, have cost alerts
- **Data loss**: Automated backups, test restore procedures
- **Service downtime**: Health checks, alerting, backup plans

---

## Next Steps After MVP Launch

### Month 2-3: Enhancements
- Advanced analytics and reporting
- Multi-project organization
- Collaboration features
- Export capabilities (PDF, Markdown)

### Month 4-6: Scale & Polish
- Performance optimization for larger datasets
- Advanced search features (faceted, date ranges)
- Mobile-responsive UI
- API for third-party integrations

### Month 6+: Advanced Features
- Fine-tuned embedding models
- Multi-language support
- Advanced visualization
- ML-powered insights

---

## Conclusion

This roadmap provides a structured path to building a production-ready research repository that balances functionality, cost, privacy, and quality. The phased approach ensures critical foundations (PII redaction, cost optimization, validation) are established before building advanced features.

The architecture decisions from the technical research reports (Pydantic validation, Presidio redaction, optimized RAG, Qdrant tuning) are integrated throughout the roadmap to ensure the final system meets the design goals.
