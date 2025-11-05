# Research Repository: Implementation Guide

## Overview

This guide walks through building a personal-scale research repository step-by-step. We'll use Railway for deployment with Qdrant (vector database) as a Railway service, keeping infrastructure simple and cost-effective.

**Tech Stack:**
- **Backend**: Python 3.11+ with FastAPI
- **Database**: PostgreSQL (Railway service)
- **Vector DB**: Qdrant (Railway service)
- **Embeddings**: OpenAI API (`text-embedding-3-small`)
- **Frontend**: Next.js 14 (deployed on Railway or Vercel)
- **Hosting**: Railway (backend + services), optional Vercel (frontend)

**Estimated Timeline**: 4-6 weeks part-time (15-20 hours/week)

---

## Phase 0: Setup & Infrastructure (Week 1)

### Step 1: Railway Account & Project Setup

1. **Create Railway Account**
   - Sign up at railway.app
   - Connect GitHub account (for deployments)

2. **Create New Project**
   - Click "New Project"
   - Name: `research-repository`

3. **Set Up Services**
   - PostgreSQL: Click "New" → "Database" → "Add PostgreSQL"
   - Qdrant: Click "New" → "Database" → Search "Qdrant" → Add Qdrant
   - Note the connection URLs from each service's "Variables" tab

### Step 2: Local Development Environment

```bash
# Create project directory
mkdir research-repository
cd research-repository

# Initialize Python virtual environment
python3.11 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Create project structure
mkdir -p app/{api,models,services,utils}
mkdir -p app/api/{v1,docs}
touch app/__init__.py
touch app/main.py
touch requirements.txt
touch .env.example
touch .gitignore
touch README.md
```

**Project Structure:**
```
research-repository/
├── app/
│   ├── api/
│   │   ├── v1/
│   │   │   ├── documents.py
│   │   │   ├── projects.py
│   │   │   ├── search.py
│   │   │   ├── missions.py
│   │   │   └── quality.py
│   │   └── deps.py  # Dependencies (DB, auth)
│   ├── models/
│   │   ├── document.py
│   │   ├── project.py
│   │   ├── chunk.py
│   │   └── mission.py
│   ├── services/
│   │   ├── chunking.py
│   │   ├── embeddings.py
│   │   ├── vector_db.py
│   │   ├── rag.py
│   │   └── quality_checks.py
│   └── utils/
│       ├── text_processing.py
│       └── validators.py
├── alembic/  # Database migrations
├── tests/
├── requirements.txt
├── .env
├── railway.json  # Railway deployment config
└── README.md
```

### Step 3: Install Dependencies

**requirements.txt:**
```txt
# Web Framework
fastapi==0.104.1
uvicorn[standard]==0.24.0
pydantic==2.5.0
pydantic-settings==2.1.0

# Database
sqlalchemy==2.0.23
alembic==1.12.1
psycopg2-binary==2.9.9
asyncpg==0.29.0

# Vector Database
qdrant-client==1.7.0

# OpenAI
openai==1.3.5

# Utilities
python-dotenv==1.0.0
python-multipart==0.0.6  # For file uploads
tiktoken==0.5.1  # Token counting
PyPDF2==3.0.1  # PDF parsing
python-docx==1.1.0  # DOCX parsing

# Testing
pytest==7.4.3
pytest-asyncio==0.21.1
httpx==0.25.2  # For testing FastAPI
```

```bash
pip install -r requirements.txt
```

### Step 4: Environment Configuration

**.env.example:**
```env
# Database
DATABASE_URL=postgresql://user:pass@localhost:5432/research_db

# Qdrant
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=

# OpenAI
OPENAI_API_KEY=sk-...

# App Config
ENVIRONMENT=development
SECRET_KEY=your-secret-key-here
```

**.env** (create from .env.example, use Railway connection strings):
```env
# From Railway PostgreSQL service
DATABASE_URL=postgresql://postgres:password@containers-us-west-xxx.railway.app:5432/railway

# From Railway Qdrant service
QDRANT_URL=https://qdrant-production-xxx.up.railway.app
QDRANT_API_KEY=your-qdrant-api-key

# OpenAI
OPENAI_API_KEY=sk-...

# App Config
ENVIRONMENT=production
SECRET_KEY=generate-with-openssl-rand-hex-32
```

### Step 5: Database Schema Setup

**app/models/base.py:**
```python
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os

DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_engine(DATABASE_URL, echo=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

**app/models/project.py:**
```python
from sqlalchemy import Column, String, Text, Integer, DateTime, ForeignKey, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from app.models.base import Base

class Project(Base):
    __tablename__ = "projects"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    description = Column(Text)
    user_id = Column(UUID(as_uuid=True), nullable=False)  # Simple single-user for now
    
    research_type = Column(String)  # 'strategic' | 'tactical' | 'generative' | 'evaluative'
    methodology = Column(String)  # 'qualitative' | 'quantitative' | 'mixed'
    status = Column(String, default='active')
    
    quality_score = Column(Integer)
    last_quality_check = Column(DateTime)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    documents = relationship("Document", back_populates="project", cascade="all, delete-orphan")
    
    __table_args__ = (
        CheckConstraint(
            "research_type IN ('strategic', 'tactical', 'generative', 'evaluative')",
            name="valid_research_type"
        ),
    )
```

**app/models/document.py:**
```python
from sqlalchemy import Column, String, Text, Integer, DateTime, ForeignKey, Boolean, Date, Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from app.models.base import Base

class Document(Base):
    __tablename__ = "documents"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"))
    name = Column(String, nullable=False)
    file_path = Column(String)
    file_type = Column(String)  # 'transcript' | 'survey' | 'notes' | 'report'
    content = Column(Text)  # Extracted text
    
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    file_size = Column(Integer)
    mime_type = Column(String)
    
    source_type = Column(String)  # 'interview' | 'survey' | 'observation'
    participant_count = Column(Integer)
    collection_date = Column(Date)
    
    processed = Column(Boolean, default=False)
    chunked = Column(Boolean, default=False)
    embedded = Column(Boolean, default=False)
    
    transcription_accuracy = Column(Numeric(3, 2))
    validation_status = Column(String, default='pending')
    
    # Relationships
    project = relationship("Project", back_populates="documents")
    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")
```

**app/models/chunk.py:**
```python
from sqlalchemy import Column, String, Text, Integer, DateTime, ForeignKey, Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from app.models.base import Base

class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"))
    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    
    embedding_id = Column(String)  # Qdrant point ID
    token_count = Column(Integer)
    start_char = Column(Integer)
    end_char = Column(Integer)
    
    prev_chunk_id = Column(UUID(as_uuid=True), ForeignKey("document_chunks.id"))
    next_chunk_id = Column(UUID(as_uuid=True), ForeignKey("document_chunks.id"))
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    document = relationship("Document", back_populates="chunks")
    
    __table_args__ = (
        {'sqlite_autoincrement': True},
    )
```

### Step 6: Initialize Database

**alembic.ini** (create via `alembic init alembic`):
```ini
[alembic]
script_location = alembic
sqlalchemy.url = postgresql://user:pass@localhost:5432/research_db

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic
```

**alembic/env.py** (modify):
```python
from app.models.base import Base
from app.models import project, document, chunk  # Import all models
target_metadata = Base.metadata
```

**Create migration:**
```bash
alembic revision --autogenerate -m "Initial schema"
alembic upgrade head
```

### Step 7: FastAPI Application Setup

**app/main.py:**
```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1 import documents, projects, search, missions, quality
from app.models.base import Base, engine
import os

app = FastAPI(
    title="Research Repository API",
    description="Personal research repository with RAG-powered search",
    version="1.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create tables (remove in production, use migrations)
if os.getenv("ENVIRONMENT") == "development":
    Base.metadata.create_all(bind=engine)

# Include routers
app.include_router(projects.router, prefix="/api/v1/projects", tags=["projects"])
app.include_router(documents.router, prefix="/api/v1/documents", tags=["documents"])
app.include_router(search.router, prefix="/api/v1/search", tags=["search"])
app.include_router(missions.router, prefix="/api/v1/missions", tags=["missions"])
app.include_router(quality.router, prefix="/api/v1/quality", tags=["quality"])

@app.get("/")
async def root():
    return {"message": "Research Repository API", "version": "1.0.0"}

@app.get("/health")
async def health():
    return {"status": "healthy"}
```

**app/api/v1/projects.py:**
```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.models.base import get_db
from app.models.project import Project
from pydantic import BaseModel
from typing import List, Optional
from uuid import UUID

router = APIRouter()

class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = None
    research_type: Optional[str] = None
    methodology: Optional[str] = None

class ProjectResponse(BaseModel):
    id: UUID
    name: str
    description: Optional[str]
    research_type: Optional[str]
    methodology: Optional[str]
    status: str
    quality_score: Optional[int]
    
    class Config:
        from_attributes = True

@router.post("/", response_model=ProjectResponse)
async def create_project(project: ProjectCreate, db: Session = Depends(get_db)):
    """Create a new research project."""
    db_project = Project(
        name=project.name,
        description=project.description,
        research_type=project.research_type,
        methodology=project.methodology,
        user_id=UUID("00000000-0000-0000-0000-000000000000")  # Single user for now
    )
    db.add(db_project)
    db.commit()
    db.refresh(db_project)
    return db_project

@router.get("/", response_model=List[ProjectResponse])
async def list_projects(db: Session = Depends(get_db)):
    """List all projects."""
    projects = db.query(Project).all()
    return projects

@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: UUID, db: Session = Depends(get_db)):
    """Get a specific project."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project
```

**Test locally:**
```bash
uvicorn app.main:app --reload --port 8000
# Visit http://localhost:8000/docs for API docs
```

---

## Phase 1: Document Management (Week 2)

### Step 8: Document Upload & Text Extraction

**app/services/text_processing.py:**
```python
import PyPDF2
from docx import Document
from typing import Optional

def extract_text_from_file(file_path: str, mime_type: str) -> str:
    """Extract text content from various file formats."""
    if mime_type == "application/pdf":
        return extract_pdf_text(file_path)
    elif mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        return extract_docx_text(file_path)
    elif mime_type == "text/plain":
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    else:
        raise ValueError(f"Unsupported file type: {mime_type}")

def extract_pdf_text(file_path: str) -> str:
    """Extract text from PDF."""
    text = ""
    with open(file_path, "rb") as f:
        pdf_reader = PyPDF2.PdfReader(f)
        for page in pdf_reader.pages:
            text += page.extract_text() + "\n"
    return text

def extract_docx_text(file_path: str) -> str:
    """Extract text from DOCX."""
    doc = Document(file_path)
    return "\n".join([paragraph.text for paragraph in doc.paragraphs])
```

**app/api/v1/documents.py:**
```python
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session
from app.models.base import get_db
from app.models.document import Document
from app.services.text_processing import extract_text_from_file
from pydantic import BaseModel
from typing import Optional
from uuid import UUID
import os
import shutil
from pathlib import Path

router = APIRouter()

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

class DocumentResponse(BaseModel):
    id: UUID
    name: str
    file_type: Optional[str]
    processed: bool
    
    class Config:
        from_attributes = True

@router.post("/", response_model=DocumentResponse)
async def upload_document(
    project_id: UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """Upload a document to a project."""
    # Save file
    file_path = UPLOAD_DIR / f"{project_id}_{file.filename}"
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    # Extract text
    try:
        content = extract_text_from_file(str(file_path), file.content_type)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to extract text: {str(e)}")
    
    # Create document record
    doc = Document(
        project_id=project_id,
        name=file.filename,
        file_path=str(file_path),
        file_type=infer_file_type(file.filename),
        content=content,
        file_size=file_path.stat().st_size,
        mime_type=file.content_type
    )
    
    db.add(doc)
    db.commit()
    db.refresh(doc)
    
    return doc

def infer_file_type(filename: str) -> str:
    """Infer document type from filename."""
    ext = filename.lower().split(".")[-1]
    if ext in ["txt", "md"]:
        return "notes"
    elif ext in ["pdf", "docx"]:
        return "report"
    else:
        return "document"
```

### Step 9: Qdrant Vector Database Setup

**app/services/vector_db.py:**
```python
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from typing import List, Dict, Any
import os
import uuid

class VectorDB:
    def __init__(self):
        qdrant_url = os.getenv("QDRANT_URL")
        qdrant_api_key = os.getenv("QDRANT_API_KEY")
        
        self.client = QdrantClient(
            url=qdrant_url,
            api_key=qdrant_api_key if qdrant_api_key else None
        )
        self.collection_name = "research_chunks"
        self.vector_size = 1536  # OpenAI text-embedding-3-small dimension
        self._ensure_collection()
    
    def _ensure_collection(self):
        """Create collection if it doesn't exist."""
        collections = self.client.get_collections().collections
        collection_names = [c.name for c in collections]
        
        if self.collection_name not in collection_names:
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=self.vector_size,
                    distance=Distance.COSINE
                )
            )
    
    def upsert_chunks(self, chunks: List[Dict[str, Any]]) -> None:
        """Store document chunks as vectors."""
        points = []
        for chunk in chunks:
            point_id = str(chunk["chunk_id"])
            point = PointStruct(
                id=point_id,
                vector=chunk["embedding"],
                payload={
                    "content": chunk["content"],
                    "document_id": str(chunk["document_id"]),
                    "project_id": str(chunk["project_id"]),
                    "chunk_index": chunk["chunk_index"],
                    "source_type": chunk.get("source_type", "unknown")
                }
            )
            points.append(point)
        
        self.client.upsert(
            collection_name=self.collection_name,
            points=points
        )
    
    def search(self, query_vector: List[float], top_k: int = 5, project_id: str = None) -> List[Dict]:
        """Search for similar chunks."""
        filter_dict = {}
        if project_id:
            filter_dict = {"must": [{"key": "project_id", "match": {"value": project_id}}]}
        
        results = self.client.search(
            collection_name=self.collection_name,
            query_vector=query_vector,
            limit=top_k,
            query_filter=filter_dict if filter_dict else None
        )
        
        return [
            {
                "chunk_id": str(result.id),
                "content": result.payload["content"],
                "document_id": result.payload["document_id"],
                "chunk_index": result.payload["chunk_index"],
                "score": result.score
            }
            for result in results
        ]

# Singleton instance
vector_db = VectorDB()
```

---

## Phase 2: RAG Pipeline (Week 3)

### Step 10: Document Chunking

**app/services/chunking.py:**
```python
import tiktoken
from typing import List, Dict
from app.services.text_processing import split_into_sentences

def chunk_document(text: str, chunk_size: int = 750, overlap: int = 50) -> List[Dict]:
    """
    Split document into overlapping chunks for embedding.
    
    Args:
        text: Document text content
        chunk_size: Target tokens per chunk
        overlap: Tokens to overlap between chunks
    
    Returns:
        List of chunk dictionaries with content and metadata
    """
    encoding = tiktoken.get_encoding("cl100k_base")  # For GPT-4
    
    sentences = split_into_sentences(text)
    chunks = []
    current_chunk = []
    current_tokens = 0
    start_char = 0
    
    for sentence in sentences:
        sentence_tokens = len(encoding.encode(sentence))
        
        if current_tokens + sentence_tokens > chunk_size and current_chunk:
            # Save current chunk
            chunk_text = " ".join(current_chunk)
            end_char = start_char + len(chunk_text)
            
            chunks.append({
                "content": chunk_text,
                "start_char": start_char,
                "end_char": end_char,
                "token_count": current_tokens
            })
            
            # Start new chunk with overlap
            overlap_text = get_overlap_text(current_chunk, overlap, encoding)
            current_chunk = overlap_text + [sentence]
            current_tokens = sum(len(encoding.encode(s)) for s in current_chunk)
            start_char = end_char - len(" ".join(overlap_text))
        else:
            current_chunk.append(sentence)
            current_tokens += sentence_tokens
    
    # Add final chunk
    if current_chunk:
        chunk_text = " ".join(current_chunk)
        chunks.append({
            "content": chunk_text,
            "start_char": start_char,
            "end_char": start_char + len(chunk_text),
            "token_count": current_tokens
        })
    
    return chunks

def split_into_sentences(text: str) -> List[str]:
    """Split text into sentences (simple implementation)."""
    import re
    # Simple sentence splitting on . ! ?
    sentences = re.split(r'(?<=[.!?])\s+', text)
    return [s.strip() for s in sentences if s.strip()]

def get_overlap_text(chunk: List[str], target_tokens: int, encoding) -> List[str]:
    """Get last N sentences that approximate target token count."""
    overlap = []
    token_count = 0
    
    for sentence in reversed(chunk):
        sentence_tokens = len(encoding.encode(sentence))
        if token_count + sentence_tokens <= target_tokens:
            overlap.insert(0, sentence)
            token_count += sentence_tokens
        else:
            break
    
    return overlap
```

### Step 11: Embedding Generation

**app/services/embeddings.py:**
```python
from openai import OpenAI
from typing import List
import os

class EmbeddingService:
    def __init__(self):
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.model = "text-embedding-3-small"
        self.dimension = 1536
    
    def generate_embedding(self, text: str) -> List[float]:
        """Generate embedding for a single text."""
        response = self.client.embeddings.create(
            model=self.model,
            input=text
        )
        return response.data[0].embedding
    
    def generate_embeddings_batch(self, texts: List[str], batch_size: int = 100) -> List[List[float]]:
        """Generate embeddings for multiple texts in batches."""
        all_embeddings = []
        
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            response = self.client.embeddings.create(
                model=self.model,
                input=batch
            )
            batch_embeddings = [item.embedding for item in response.data]
            all_embeddings.extend(batch_embeddings)
        
        return all_embeddings

# Singleton instance
embedding_service = EmbeddingService()
```

### Step 12: Process Document Pipeline

**app/api/v1/documents.py** (add processing endpoint):
```python
from app.services.chunking import chunk_document
from app.services.embeddings import embedding_service
from app.services.vector_db import vector_db
from app.models.chunk import DocumentChunk

@router.post("/{document_id}/process")
async def process_document(
    document_id: UUID,
    db: Session = Depends(get_db)
):
    """Process document: chunk, embed, and store in vector DB."""
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    if not doc.content:
        raise HTTPException(status_code=400, detail="Document has no content")
    
    # Chunk document
    chunks_data = chunk_document(doc.content)
    
    # Create chunk records
    chunk_objects = []
    for i, chunk_data in enumerate(chunks_data):
        chunk = DocumentChunk(
            document_id=doc.id,
            chunk_index=i,
            content=chunk_data["content"],
            token_count=chunk_data["token_count"],
            start_char=chunk_data["start_char"],
            end_char=chunk_data["end_char"]
        )
        chunk_objects.append(chunk)
        db.add(chunk)
    
    db.commit()
    
    # Generate embeddings
    chunk_texts = [chunk.content for chunk in chunk_objects]
    embeddings = embedding_service.generate_embeddings_batch(chunk_texts)
    
    # Prepare for vector DB
    vector_chunks = []
    for chunk, embedding in zip(chunk_objects, embeddings):
        vector_chunks.append({
            "chunk_id": str(chunk.id),
            "content": chunk.content,
            "document_id": doc.id,
            "project_id": doc.project_id,
            "chunk_index": chunk.chunk_index,
            "embedding": embedding,
            "source_type": doc.source_type or "unknown"
        })
        
        # Store embedding ID in chunk
        chunk.embedding_id = str(chunk.id)
    
    # Store in vector DB
    vector_db.upsert_chunks(vector_chunks)
    
    # Mark document as processed
    doc.chunked = True
    doc.embedded = True
    doc.processed = True
    db.commit()
    
    return {
        "message": "Document processed successfully",
        "chunks_created": len(chunks_data)
    }
```

---

## Phase 3: Semantic Search & RAG (Week 4)

### Step 13: RAG Query Service

**app/services/rag.py:**
```python
from openai import OpenAI
from app.services.embeddings import embedding_service
from app.services.vector_db import vector_db
from typing import List, Dict
import os

class RAGService:
    def __init__(self):
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.model = "gpt-4-turbo-preview"  # Or gpt-3.5-turbo for cost savings
    
    def query(self, query: str, project_id: str = None, top_k: int = 5) -> Dict:
        """Perform RAG query: retrieve context and generate answer."""
        # Generate query embedding
        query_embedding = embedding_service.generate_embedding(query)
        
        # Retrieve relevant chunks
        search_results = vector_db.search(
            query_vector=query_embedding,
            top_k=top_k,
            project_id=str(project_id) if project_id else None
        )
        
        if not search_results:
            return {
                "answer": "I couldn't find any relevant information in the research data.",
                "sources": []
            }
        
        # Assemble context
        context_chunks = "\n\n".join([
            f"[Source {i+1}]: {result['content']}"
            for i, result in enumerate(search_results)
        ])
        
        # Generate answer with citations
        prompt = f"""You are a research assistant analyzing user research data.

Context from research documents:
{context_chunks}

User Question: {query}

Instructions:
- Answer ONLY based on the provided context
- If information is not in the context, say "I don't have information about that in the research data"
- For each claim, cite the specific source using [Source 1], [Source 2], etc.
- Be concise and accurate

Answer:"""
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "You are a helpful research assistant."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1  # Lower temperature for more factual responses
        )
        
        answer = response.choices[0].message.content
        
        # Format sources with metadata
        sources = [
            {
                "chunk_id": result["chunk_id"],
                "content": result["content"],
                "document_id": result["document_id"],
                "score": result["score"]
            }
            for result in search_results
        ]
        
        return {
            "answer": answer,
            "sources": sources,
            "query": query
        }

# Singleton instance
rag_service = RAGService()
```

### Step 14: Search API Endpoints

**app/api/v1/search.py:**
```python
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.models.base import get_db
from app.services.rag import rag_service
from app.services.embeddings import embedding_service
from app.services.vector_db import vector_db
from pydantic import BaseModel
from typing import Optional
from uuid import UUID

router = APIRouter()

class RAGQuery(BaseModel):
    query: str
    project_id: Optional[UUID] = None
    top_k: int = 5

class RAGResponse(BaseModel):
    answer: str
    sources: list
    query: str

@router.post("/rag", response_model=RAGResponse)
async def rag_query(query: RAGQuery):
    """Perform RAG query with semantic search and LLM generation."""
    result = rag_service.query(
        query=query.query,
        project_id=str(query.project_id) if query.project_id else None,
        top_k=query.top_k
    )
    return result

@router.post("/semantic")
async def semantic_search(
    query: str = Query(..., description="Search query"),
    project_id: Optional[UUID] = Query(None),
    top_k: int = Query(5, ge=1, le=20)
):
    """Semantic search without LLM generation (just retrieval)."""
    query_embedding = embedding_service.generate_embedding(query)
    
    results = vector_db.search(
        query_vector=query_embedding,
        top_k=top_k,
        project_id=str(project_id) if project_id else None
    )
    
    return {
        "query": query,
        "results": results,
        "count": len(results)
    }
```

---

## Phase 4: Deploy to Railway (Week 5)

### Step 15: Railway Configuration

**railway.json:**
```json
{
  "$schema": "https://railway.app/railway.schema.json",
  "build": {
    "builder": "NIXPACKS"
  },
  "deploy": {
    "startCommand": "uvicorn app.main:app --host 0.0.0.0 --port $PORT",
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 10
  }
}
```

**Procfile** (alternative):
```
web: uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

**.railwayignore:**
```
venv/
__pycache__/
*.pyc
.env
uploads/
tests/
alembic/versions/*.pyc
```

### Step 16: Deploy

1. **Connect GitHub Repository**
   - Push code to GitHub
   - In Railway, click "New Project" → "Deploy from GitHub repo"
   - Select your repository

2. **Set Environment Variables**
   - Go to project settings → Variables
   - Add all variables from `.env`
   - Railway will auto-inject `DATABASE_URL` and `QDRANT_URL` from services

3. **Deploy**
   - Railway auto-deploys on push to main branch
   - Check deployment logs in Railway dashboard
   - Test API at `https://your-project.up.railway.app/docs`

### Step 17: Database Migrations on Railway

**Update Railway deployment to run migrations:**

**railway.json** (add build step):
```json
{
  "build": {
    "builder": "NIXPACKS",
    "buildCommand": "pip install -r requirements.txt && alembic upgrade head"
  }
}
```

Or add migration as a separate service:
- Create new service: "Migration Runner"
- Command: `alembic upgrade head`
- Run on deploy

---

## Phase 5: Quality Tools & Mission Protocol (Week 6+)

### Step 18: Implement Quality Checks

See `technical_architecture.md` for detailed quality gate implementations. Key files:
- `app/services/quality_checks.py` - Bias, traceability, rigor checkers
- `app/api/v1/quality.py` - Quality check API endpoints

### Step 19: Mission Protocol Integration

See `technical_architecture.md` for Mission Protocol schema. Key files:
- `app/models/mission.py` - Mission data model
- `app/services/mission_protocol.py` - Validation and quality gate enforcement
- `app/api/v1/missions.py` - Mission CRUD and YAML export/import

---

## Testing & Validation

### Test RAG Pipeline

```python
# tests/test_rag.py
import pytest
from app.services.rag import rag_service

def test_rag_query():
    result = rag_service.query(
        "What are the main user pain points?",
        top_k=3
    )
    assert "answer" in result
    assert "sources" in result
    assert len(result["sources"]) > 0
```

### Test Vector Search

```python
# tests/test_vector_db.py
from app.services.vector_db import vector_db

def test_vector_search():
    # Test embedding
    test_vector = [0.1] * 1536
    results = vector_db.search(test_vector, top_k=5)
    assert isinstance(results, list)
```

---

## Cost Estimates

**Monthly Costs (Personal Scale):**
- Railway Hobby Plan: $5/month (500 hours compute)
- PostgreSQL (Railway): Included or ~$5/month
- Qdrant (Railway): ~$5/month
- OpenAI Embeddings: ~$1-5/month (depends on usage)
  - 1M tokens = $0.02
  - 50K chunks = ~$1-2/month
- OpenAI GPT-4 for RAG: ~$10-50/month (depends on queries)
  - Or use GPT-3.5-turbo: ~$1-5/month

**Total: ~$22-70/month** for full functionality

---

## Next Steps

1. **Frontend Development**: Build Next.js UI for document upload and search
2. **Mission Protocol UI**: Create forms for Mission Protocol creation
3. **Quality Dashboard**: Visualize quality scores and recommendations
4. **Advanced Features**: Bias detection, traceability validator, rigor checker

See `technical_architecture.md` for detailed specifications of these features.

