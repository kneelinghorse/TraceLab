#!/usr/bin/env python3
"""
Embedding Reprocessing Script

Rebuilds the entire Qdrant vector store from PostgreSQL source of truth.
Enables recovery from Qdrant data loss and supports embedding model upgrades.

Usage:
    # Dry run - show what would be processed with cost estimate
    python scripts/reprocess_embeddings.py --dry-run

    # Full rebuild from scratch
    python scripts/reprocess_embeddings.py

    # Resume from a specific document ID (alphabetical UUID ordering)
    python scripts/reprocess_embeddings.py --resume-from <document-uuid>

    # Process only specific project
    python scripts/reprocess_embeddings.py --project-id <project-uuid>

    # Drop collection and start fresh
    python scripts/reprocess_embeddings.py --drop-collection
"""
import sys
import os
import argparse
import time
from datetime import datetime
from typing import Optional
from uuid import UUID

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.document import Document
from app.models.chunk import DocumentChunk
from app.services.embedding_service import get_embedding_service
from app.services.qdrant_service import get_qdrant_service


# Cost estimation constants (OpenAI text-embedding-3-small)
COST_PER_1K_TOKENS = 0.00002  # $0.02 per 1M tokens = $0.00002 per 1K tokens
AVG_TOKENS_PER_CHUNK = 750  # Conservative estimate


class ProgressTracker:
    """Tracks and displays progress during reprocessing."""

    def __init__(self, total_documents: int, total_chunks: int):
        self.total_documents = total_documents
        self.total_chunks = total_chunks
        self.processed_documents = 0
        self.processed_chunks = 0
        self.failed_documents = []
        self.start_time = time.time()

    def update(self, doc_name: str, chunk_count: int, success: bool = True):
        """Update progress after processing a document."""
        self.processed_documents += 1
        if success:
            self.processed_chunks += chunk_count
        else:
            self.failed_documents.append(doc_name)

        elapsed = time.time() - self.start_time
        docs_per_sec = self.processed_documents / elapsed if elapsed > 0 else 0
        remaining_docs = self.total_documents - self.processed_documents
        eta_seconds = remaining_docs / docs_per_sec if docs_per_sec > 0 else 0

        # Format ETA
        if eta_seconds > 3600:
            eta_str = f"{eta_seconds / 3600:.1f}h"
        elif eta_seconds > 60:
            eta_str = f"{eta_seconds / 60:.1f}m"
        else:
            eta_str = f"{eta_seconds:.0f}s"

        status = "✓" if success else "✗"
        print(
            f"[{self.processed_documents}/{self.total_documents}] {status} {doc_name}: "
            f"{chunk_count} chunks | ETA: {eta_str}"
        )

    def summary(self):
        """Print final summary."""
        elapsed = time.time() - self.start_time
        print("\n" + "=" * 60)
        print("REPROCESSING COMPLETE")
        print("=" * 60)
        print(f"Documents processed: {self.processed_documents}/{self.total_documents}")
        print(f"Chunks embedded: {self.processed_chunks}/{self.total_chunks}")
        print(f"Time elapsed: {elapsed / 60:.1f} minutes")

        if self.failed_documents:
            print(f"\nFailed documents ({len(self.failed_documents)}):")
            for doc in self.failed_documents:
                print(f"  - {doc}")

        # Estimate actual cost
        est_tokens = self.processed_chunks * AVG_TOKENS_PER_CHUNK
        est_cost = (est_tokens / 1000) * COST_PER_1K_TOKENS
        print(f"\nEstimated API cost: ${est_cost:.4f}")


def get_document_stats(
    db: Session,
    resume_from: Optional[UUID] = None,
    project_id: Optional[UUID] = None
) -> tuple[int, int]:
    """Get total document and chunk counts for progress tracking."""
    doc_query = db.query(Document).filter(Document.chunked == True)

    if project_id:
        doc_query = doc_query.filter(Document.project_id == project_id)

    if resume_from:
        doc_query = doc_query.filter(Document.id > str(resume_from))

    doc_count = doc_query.count()

    # Count chunks across those documents
    chunk_count = db.query(func.count(DocumentChunk.id)).join(Document).filter(
        Document.chunked == True
    )
    if project_id:
        chunk_count = chunk_count.filter(Document.project_id == project_id)
    if resume_from:
        chunk_count = chunk_count.filter(Document.id > str(resume_from))

    chunk_count = chunk_count.scalar() or 0

    return doc_count, chunk_count


def dry_run(
    db: Session,
    resume_from: Optional[UUID] = None,
    project_id: Optional[UUID] = None
):
    """Show what would be processed without making API calls."""
    print("\n" + "=" * 60)
    print("DRY RUN - No API calls will be made")
    print("=" * 60 + "\n")

    doc_query = db.query(Document).filter(Document.chunked == True)

    if project_id:
        doc_query = doc_query.filter(Document.project_id == project_id)

    if resume_from:
        doc_query = doc_query.filter(Document.id > str(resume_from))

    documents = doc_query.order_by(Document.id).all()

    total_chunks = 0
    doc_details = []

    for doc in documents:
        chunk_count = db.query(func.count(DocumentChunk.id)).filter(
            DocumentChunk.document_id == doc.id
        ).scalar() or 0

        total_chunks += chunk_count
        doc_details.append((doc.name, chunk_count, doc.id))
        print(f"[DRY RUN] {doc.name}: {chunk_count} chunks")

    # Cost estimation
    est_tokens = total_chunks * AVG_TOKENS_PER_CHUNK
    est_cost = (est_tokens / 1000) * COST_PER_1K_TOKENS

    print("\n" + "-" * 60)
    print("SUMMARY")
    print("-" * 60)
    print(f"Documents to process: {len(documents)}")
    print(f"Total chunks: {total_chunks}")
    print(f"Estimated tokens: {est_tokens:,}")
    print(f"Estimated cost: ${est_cost:.4f}")

    # Time estimate (conservative: 50 chunks/second with batching)
    chunks_per_second = 50
    est_seconds = total_chunks / chunks_per_second
    if est_seconds > 3600:
        time_str = f"{est_seconds / 3600:.1f} hours"
    elif est_seconds > 60:
        time_str = f"{est_seconds / 60:.1f} minutes"
    else:
        time_str = f"{est_seconds:.0f} seconds"
    print(f"Estimated time: {time_str}")

    if resume_from:
        print(f"\n(Resuming from document ID: {resume_from})")

    if project_id:
        print(f"(Filtered to project ID: {project_id})")

    print("\nRun without --dry-run to execute the reprocessing.")


def reprocess_embeddings(
    db: Session,
    embedding_service,
    qdrant_service,
    resume_from: Optional[UUID] = None,
    project_id: Optional[UUID] = None,
    drop_collection: bool = False
):
    """Regenerate all embeddings from PostgreSQL chunks."""

    # Optionally drop collection for fresh start
    if drop_collection:
        print("Dropping existing Qdrant collection...")
        try:
            qdrant_service.client.delete_collection(qdrant_service.collection_name)
            print(f"Collection '{qdrant_service.collection_name}' dropped.")
        except Exception as e:
            print(f"Could not drop collection (may not exist): {e}")

    # Ensure collection exists with write-optimized settings
    print("Ensuring Qdrant collection exists (write-optimized mode)...")
    qdrant_service.ensure_collection(write_optimized=True)

    # Build query for documents to process
    doc_query = db.query(Document).filter(Document.chunked == True)

    if project_id:
        doc_query = doc_query.filter(Document.project_id == project_id)

    if resume_from:
        doc_query = doc_query.filter(Document.id > str(resume_from))

    documents = doc_query.order_by(Document.id).all()

    if not documents:
        print("No documents to process.")
        return

    # Get stats for progress tracking
    total_docs = len(documents)
    total_chunks = sum(
        db.query(func.count(DocumentChunk.id)).filter(
            DocumentChunk.document_id == doc.id
        ).scalar() or 0
        for doc in documents
    )

    print(f"\nProcessing {total_docs} documents ({total_chunks} chunks)...\n")

    tracker = ProgressTracker(total_docs, total_chunks)

    for doc in documents:
        try:
            # Get chunks for this document
            chunks = db.query(DocumentChunk).filter(
                DocumentChunk.document_id == doc.id
            ).order_by(DocumentChunk.chunk_index).all()

            if not chunks:
                tracker.update(doc.name, 0, success=True)
                continue

            # Generate embeddings in batch
            texts = [chunk.content for chunk in chunks]
            embeddings = embedding_service.generate_embeddings_batch(texts)

            # Prepare Qdrant payload
            payload = []
            for chunk, embedding in zip(chunks, embeddings):
                # Update embedding_id in PostgreSQL
                chunk.embedding_id = str(chunk.id)

                payload.append({
                    "chunk_id": chunk.id,
                    "embedding": embedding,
                    "content": chunk.content,
                    "document_id": doc.id,
                    "project_id": doc.project_id,
                    "chunk_index": chunk.chunk_index,
                    "source_type": doc.source_type,
                })

            # Upsert to Qdrant
            qdrant_service.upsert_chunks(payload)

            # Mark document as embedded and commit
            doc.embedded = True
            db.commit()

            tracker.update(doc.name, len(chunks), success=True)

        except Exception as e:
            db.rollback()
            print(f"ERROR processing {doc.name}: {e}")
            tracker.update(doc.name, 0, success=False)

    # Enable indexing and quantization after bulk import
    print("\nEnabling HNSW indexing and quantization...")
    try:
        qdrant_service.enable_indexing_and_quantization()
        print("Indexing enabled successfully.")
    except Exception as e:
        print(f"Warning: Could not enable indexing: {e}")

    tracker.summary()

    # Print last processed document ID for resume capability
    if documents:
        last_doc = documents[-1]
        print(f"\nLast processed document ID: {last_doc.id}")
        print(f"To resume from here: --resume-from {last_doc.id}")


def main():
    parser = argparse.ArgumentParser(
        description="Rebuild Qdrant embeddings from PostgreSQL source of truth",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Preview what would be processed
  python scripts/reprocess_embeddings.py --dry-run

  # Full rebuild
  python scripts/reprocess_embeddings.py

  # Resume from specific document
  python scripts/reprocess_embeddings.py --resume-from abc123...

  # Fresh start (drop collection first)
  python scripts/reprocess_embeddings.py --drop-collection
        """
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be processed without making API calls"
    )

    parser.add_argument(
        "--resume-from",
        type=str,
        metavar="UUID",
        help="Resume processing from this document UUID (alphabetical ordering)"
    )

    parser.add_argument(
        "--project-id",
        type=str,
        metavar="UUID",
        help="Only process documents from this project"
    )

    parser.add_argument(
        "--drop-collection",
        action="store_true",
        help="Drop existing Qdrant collection before rebuild (fresh start)"
    )

    args = parser.parse_args()

    # Parse UUIDs if provided
    resume_from = UUID(args.resume_from) if args.resume_from else None
    project_id = UUID(args.project_id) if args.project_id else None

    print("=" * 60)
    print("TRACELAB EMBEDDING REPROCESSING")
    print(f"Started: {datetime.now().isoformat()}")
    print("=" * 60)

    # Create database session
    db = SessionLocal()

    try:
        if args.dry_run:
            dry_run(db, resume_from=resume_from, project_id=project_id)
        else:
            # Confirm if dropping collection
            if args.drop_collection:
                confirm = input(
                    "\nWARNING: This will delete the entire Qdrant collection.\n"
                    "Type 'yes' to confirm: "
                )
                if confirm.lower() != "yes":
                    print("Aborted.")
                    return

            # Initialize services
            print("\nInitializing services...")
            embedding_service = get_embedding_service()
            qdrant_service = get_qdrant_service()

            reprocess_embeddings(
                db=db,
                embedding_service=embedding_service,
                qdrant_service=qdrant_service,
                resume_from=resume_from,
                project_id=project_id,
                drop_collection=args.drop_collection
            )

    finally:
        db.close()

    print(f"\nCompleted: {datetime.now().isoformat()}")


if __name__ == "__main__":
    main()
