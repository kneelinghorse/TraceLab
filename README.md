# TraceLab Research Repository

Personal-scale research repository with RAG-powered semantic search, structured data organization, and quality-enforced workflows.

## Tech Stack

- **Backend**: Python 3.11+ with FastAPI
- **Database**: PostgreSQL 15
- **Migrations**: Alembic
- **Containerization**: Docker & Docker Compose

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Python 3.11+ (for local development without Docker)

### Development Setup

1. **Clone the repository and navigate to the project:**
   ```bash
   cd TraceLab
   ```

2. **Copy environment file:**
   ```bash
   cp .env.example .env
   ```
   Edit `.env` with your configuration if needed.

3. **Start services with Docker Compose:**
   ```bash
   docker-compose up -d
   ```
   
   This will:
   - Start PostgreSQL on port 5432
   - Build and start the FastAPI application on port 8000

4. **Run database migrations:**
   ```bash
   docker-compose exec app alembic upgrade head
   ```

5. **Access the API:**
   - API docs: http://localhost:8000/docs
   - Health check: http://localhost:8000/api/v1/health
   - DB health check: http://localhost:8000/api/v1/health/db

### Local Development (Without Docker)

1. **Create virtual environment:**
   ```bash
   python3.11 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Start PostgreSQL** (ensure PostgreSQL is running locally or via Docker):
   ```bash
   docker-compose up -d postgres
   ```

4. **Run migrations:**
   ```bash
   alembic upgrade head
   ```

5. **Start the development server:**
   ```bash
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

## Project Structure

```
TraceLab/
├── app/
│   ├── api/           # API endpoints
│   │   └── v1/        # API v1 routes
│   ├── core/          # Core configuration and database
│   ├── models/        # SQLAlchemy models
│   ├── services/      # Business logic services
│   └── utils/         # Utility functions
├── alembic/           # Database migrations
├── tests/             # Test files
├── docker-compose.yml  # Docker Compose configuration
├── Dockerfile         # Application Dockerfile
└── requirements.txt   # Python dependencies
```

## Database Schema

The application uses the following core tables:

- `projects` - Research projects
- `documents` - Uploaded research documents
- `document_chunks` - Chunks for RAG embeddings
- `tags` - Tag taxonomy
- `document_tags` - Document-tag relationships
- `insights` - Synthesized findings
- `insight_sources` - Insight-source chunk relationships
- `missions` - Mission Protocol integration (JSONB)
- `quality_checks` - Quality audit trail

See `cmos/docs/technical_architecture.md` for detailed schema documentation.

## Migrations

### Create a new migration:
```bash
alembic revision --autogenerate -m "description"
```

### Apply migrations:
```bash
alembic upgrade head
```

### Rollback:
```bash
alembic downgrade -1
```

## Testing

Run health checks:
```bash
# Basic health
curl http://localhost:8000/api/v1/health

# Database health
curl http://localhost:8000/api/v1/health/db
```

## Synthetic Corpus Pipeline (B1.2)

Regenerate the synthetic UX research corpus (Markdown, TXT, DOCX, PDF, CSV) populated with locale-aware Faker PII:

```bash
python scripts/generate_corpus.py
```

Evaluate Presidio against the corpus and capture the baseline metrics artifact:

```bash
python scripts/evaluate_presidio.py
```

Package the corpus for secure upload (creates archive, manifest, and baseline copy):

```bash
python scripts/package_corpus.py
python scripts/upload_corpus.py --destination /secure/presidio/upload
```

Refer to `data/corpus/README.md` for detailed options (document counts, survey rows, research briefs) and storage guidance.

## Development Notes

- The application creates tables automatically in development mode
- Use Alembic migrations for production deployments
- Database connection settings are managed via environment variables
- CORS is enabled for development (configure appropriately for production)

## Next Steps

This repo now includes:
- B1.1: Core Service Bootstrap
- B1.2: Synthetic Corpus Pipeline (corpus generator, annotations, evaluation harness)

Upcoming missions:
- B1.3: Presidio Redaction Service
- B1.4: Document Ingestion Pipeline
- B1.5: Embedding & Qdrant Bootstrap
