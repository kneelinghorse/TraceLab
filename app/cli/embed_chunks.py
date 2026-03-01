"""CLI script to process pending document chunks and generate embeddings."""
import argparse
import sys
import time
from pathlib import Path
from typing import List, Dict, Any
from sqlalchemy.orm import Session

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.core.database import SessionLocal
from app.models.chunk import DocumentChunk
from app.models.document import Document
from app.services.embedding_service import get_embedding_service
from app.services.qdrant_service import get_qdrant_service


def get_pending_chunks(db: Session, batch_size: int = 100) -> List[DocumentChunk]:
    """Get chunks that haven't been embedded yet."""
    return db.query(DocumentChunk).filter(
        DocumentChunk.embedding_id.is_(None)
    ).limit(batch_size).all()


def process_chunks(
    chunks: List[DocumentChunk],
    embedding_service,
    qdrant_service,
    db: Session,
    batch_size: int = 100
) -> Dict[str, Any]:
    """
    Process chunks: generate embeddings and store in Qdrant.
    
    Returns metrics dict with:
        - processed_count: Number of chunks processed
        - total_tokens: Total tokens embedded
        - total_time: Processing time in seconds
        - avg_latency: Average latency per chunk
    """
    if not chunks:
        return {
            "processed_count": 0,
            "total_tokens": 0,
            "total_time": 0.0,
            "avg_latency": 0.0
        }
    
    start_time = time.time()
    processed_count = 0
    total_tokens = 0
    
    # Process in batches for embedding generation
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i + batch_size]
        
        # Extract texts
        texts = [chunk.content for chunk in batch]
        
        # Generate embeddings
        try:
            embeddings = embedding_service.generate_embeddings_batch(texts, batch_size=batch_size)
        except Exception as e:
            print(f"Error generating embeddings for batch {i//batch_size + 1}: {e}")
            continue
        
        # Prepare chunks for Qdrant
        qdrant_chunks = []
        for chunk, embedding in zip(batch, embeddings):
            # Get document to extract metadata
            document = db.query(Document).filter(Document.id == chunk.document_id).first()
            if not document:
                continue
            
            qdrant_chunk = {
                "chunk_id": str(chunk.id),
                "embedding": embedding,
                "content": chunk.content,
                "document_id": str(chunk.document_id),
                "project_id": str(document.project_id),
                "chunk_index": chunk.chunk_index,
                "source_type": document.source_type
            }
            qdrant_chunks.append(qdrant_chunk)
            
            # Count tokens (approximate)
            total_tokens += len(chunk.content.split())  # Rough token estimate
        
        # Store in Qdrant
        try:
            qdrant_service.upsert_chunks(qdrant_chunks, batch_size=100, parallel=2)
            
            # Update chunks in database
            for chunk, qdrant_chunk in zip(batch, qdrant_chunks):
                chunk.embedding_id = qdrant_chunk["chunk_id"]
                processed_count += 1
            
            # Update document embedded status
            document_ids = set(str(chunk.document_id) for chunk in batch)
            for doc_id in document_ids:
                doc = db.query(Document).filter(Document.id == doc_id).first()
                if doc:
                    doc.embedded = True
            
            db.commit()
            
        except Exception as e:
            print(f"Error storing embeddings in Qdrant for batch {i//batch_size + 1}: {e}")
            db.rollback()
            continue
    
    total_time = time.time() - start_time
    avg_latency = total_time / processed_count if processed_count > 0 else 0.0
    
    return {
        "processed_count": processed_count,
        "total_tokens": total_tokens,
        "total_time": total_time,
        "avg_latency": avg_latency
    }


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Generate embeddings for pending chunks and load them into Qdrant."
    )
    parser.add_argument(
        "--phase",
        choices=["prepare", "ingest", "finalize", "full"],
        default="ingest",
        help=(
            "prepare: ensure collection in write-optimized mode without ingesting;"
            " ingest: process chunks using current collection configuration;"
            " finalize: enable HNSW and quantization;"
            " full: prepare, ingest, and finalize in one run."
        )
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Number of chunks per embedding batch."
    )
    parser.add_argument(
        "--max-chunks",
        type=int,
        default=None,
        help="Optional cap on the number of chunks processed in this run."
    )
    return parser.parse_args()


def main():
    """Main CLI entry point."""
    args = parse_args()
    print(f"Starting chunk embedding process (phase={args.phase})...")
    
    # Initialize services
    try:
        embedding_service = get_embedding_service()
        qdrant_service = get_qdrant_service()
    except Exception as e:
        print(f"Error initializing services: {e}")
        sys.exit(1)
    
    # Phase-specific handling
    try:
        if args.phase == "prepare":
            qdrant_service.ensure_collection(write_optimized=True)
            print("Qdrant collection prepared in write-optimized mode for bulk ingest.")
            return
        if args.phase == "finalize":
            qdrant_service.enable_indexing_and_quantization()
            print("Qdrant collection indexing and quantization enabled.")
            return
        
        # Determine whether to prepare collection for bulk ingest
        write_optimized = args.phase == "full"
        qdrant_service.ensure_collection(write_optimized=write_optimized)
    except Exception as e:
        print(f"Error configuring Qdrant collection: {e}")
        sys.exit(1)
    
    # Process chunks
    db = SessionLocal()
    try:
        total_processed = 0
        batch_count = 0
        
        while True:
            if args.max_chunks is not None:
                remaining = args.max_chunks - total_processed
                if remaining <= 0:
                    print("Reached max chunk limit for this run.")
                    break
                batch_size = min(args.batch_size, remaining)
            else:
                batch_size = args.batch_size
            
            chunks = get_pending_chunks(db, batch_size=batch_size)
            if not chunks:
                if total_processed == 0:
                    print("No pending chunks to process.")
                break
            
            batch_count += 1
            print(f"Processing batch {batch_count} ({len(chunks)} chunks)...")
            
            metrics = process_chunks(
                chunks,
                embedding_service,
                qdrant_service,
                db,
                batch_size=args.batch_size
            )
            
            total_processed += metrics["processed_count"]
            print(
                f"Batch {batch_count} complete: "
                f"{metrics['processed_count']} chunks, "
                f"{metrics['total_tokens']} tokens, "
                f"{metrics['total_time']:.2f}s, "
                f"{metrics['avg_latency']:.3f}s/chunk"
            )
            
            if metrics["processed_count"] < len(chunks):
                # Something prevented full batch ingestion (errors already logged)
                break
        
        print(f"\nTotal processed: {total_processed} chunks")
        
        if args.phase == "full" and total_processed > 0:
            print("Finalizing Qdrant collection (enabling HNSW + quantization)...")
            qdrant_service.enable_indexing_and_quantization()
            print("Qdrant collection finalized.")
        
    finally:
        db.close()


if __name__ == "__main__":
    main()
