"""
Document chunking service for RAG.

Splits documents into overlapping chunks of 500-1000 tokens as specified
in the technical architecture.
"""

import re
from dataclasses import dataclass


@dataclass
class Chunk:
    """Represents a document chunk."""

    content: str
    chunk_index: int
    start_char: int
    end_char: int
    token_count: int


class ChunkingService:
    """Service for chunking documents into overlapping segments."""

    def __init__(
        self,
        target_chunk_size: int = 750,
        chunk_overlap: int = 50,
        min_chunk_size: int = 500,
        max_chunk_size: int = 1000,
    ):
        """
        Initialize chunking service.

        Args:
            target_chunk_size: Target token count per chunk (default: 750)
            chunk_overlap: Overlap in tokens between chunks (default: 50)
            min_chunk_size: Minimum tokens per chunk (default: 500)
            max_chunk_size: Maximum tokens per chunk (default: 1000)
        """
        self.target_chunk_size = target_chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk_size = min_chunk_size
        self.max_chunk_size = max_chunk_size

    def chunk_document(self, text: str) -> list[Chunk]:
        """
        Split document into overlapping chunks.

        Preserves sentence boundaries and maintains context through overlap.

        Args:
            text: Document text to chunk

        Returns:
            List of Chunk objects with content, indices, positions, and token counts
        """
        if not text.strip():
            return []

        # Split into sentences (simple regex-based approach)
        sentences = self._split_into_sentences(text)

        if not sentences:
            return []

        chunks = []
        current_chunk_sentences = []
        current_chunk_start = 0
        current_token_count = 0
        chunk_index = 0

        for sentence in sentences:
            sentence_tokens = self._count_tokens(sentence)
            sentence_start = text.find(sentence, current_chunk_start)
            sentence_end = sentence_start + len(sentence)

            # Check if adding this sentence would exceed max chunk size
            if (
                current_token_count + sentence_tokens > self.max_chunk_size
                and current_chunk_sentences
            ):
                # Save current chunk if it meets minimum size
                if current_token_count >= self.min_chunk_size:
                    chunk_end = current_chunk_start + sum(
                        len(s) for s in current_chunk_sentences
                    )
                    chunk_content = " ".join(current_chunk_sentences)
                    chunks.append(
                        Chunk(
                            content=chunk_content,
                            chunk_index=chunk_index,
                            start_char=current_chunk_start,
                            end_char=chunk_end,
                            token_count=current_token_count,
                        )
                    )
                    chunk_index += 1

                    # Start new chunk with overlap
                    overlap_sentences = self._get_overlap_sentences(
                        current_chunk_sentences, self.chunk_overlap
                    )
                    current_chunk_sentences = overlap_sentences + [sentence]
                    current_token_count = sum(
                        self._count_tokens(s) for s in current_chunk_sentences
                    )
                    current_chunk_start = sentence_start
                else:
                    # Current chunk too small, continue adding
                    current_chunk_sentences.append(sentence)
                    current_token_count += sentence_tokens
            else:
                # Add sentence to current chunk
                current_chunk_sentences.append(sentence)
                current_token_count += sentence_tokens

                # If we've reached target size, consider finalizing chunk
                if current_token_count >= self.target_chunk_size:
                    # Check if we should split here (prefer sentence boundaries near target)
                    if len(current_chunk_sentences) > 1:
                        chunk_end = current_chunk_start + sum(
                            len(s) for s in current_chunk_sentences
                        )
                        chunk_content = " ".join(current_chunk_sentences)
                        chunks.append(
                            Chunk(
                                content=chunk_content,
                                chunk_index=chunk_index,
                                start_char=current_chunk_start,
                                end_char=chunk_end,
                                token_count=current_token_count,
                            )
                        )
                        chunk_index += 1

                        # Start new chunk with overlap
                        overlap_sentences = self._get_overlap_sentences(
                            current_chunk_sentences, self.chunk_overlap
                        )
                        current_chunk_sentences = overlap_sentences
                        current_token_count = sum(
                            self._count_tokens(s) for s in overlap_sentences
                        )
                        current_chunk_start = sentence_start

        # Add final chunk if it exists and meets minimum size
        if current_chunk_sentences and current_token_count >= self.min_chunk_size:
            chunk_end = current_chunk_start + sum(
                len(s) for s in current_chunk_sentences
            )
            chunk_content = " ".join(current_chunk_sentences)
            chunks.append(
                Chunk(
                    content=chunk_content,
                    chunk_index=chunk_index,
                    start_char=current_chunk_start,
                    end_char=chunk_end,
                    token_count=current_token_count,
                )
            )

        return chunks

    def _split_into_sentences(self, text: str) -> list[str]:
        """
        Split text into sentences using regex.

        Simple sentence splitting based on punctuation.
        """
        # Pattern matches sentence endings (. ! ?) followed by whitespace or end of string
        sentence_endings = re.compile(r"([.!?]+)\s+")

        sentences = []
        last_end = 0

        for match in sentence_endings.finditer(text):
            sentence = text[last_end : match.end()].strip()
            if sentence:
                sentences.append(sentence)
            last_end = match.end()

        # Add remaining text as final sentence
        remaining = text[last_end:].strip()
        if remaining:
            sentences.append(remaining)

        # If no sentence endings found, treat entire text as one sentence
        if not sentences and text.strip():
            sentences = [text.strip()]

        return sentences

    def _count_tokens(self, text: str) -> int:
        """
        Estimate token count using simple heuristic.

        Uses approximation: ~4 characters per token for English text.
        This is a rough estimate; actual token counts depend on the tokenizer.
        """
        # Simple approximation: average English token is ~4 characters
        # This works well enough for chunk sizing
        char_count = len(text)
        return max(1, char_count // 4)

    def _get_overlap_sentences(
        self, sentences: list[str], target_overlap_tokens: int
    ) -> list[str]:
        """
        Get the last N sentences that approximate target overlap token count.

        Args:
            sentences: List of sentences
            target_overlap_tokens: Target number of tokens for overlap

        Returns:
            List of sentences to use for overlap
        """
        if not sentences:
            return []

        overlap_sentences = []
        overlap_tokens = 0

        # Work backwards from the end
        for sentence in reversed(sentences):
            sentence_tokens = self._count_tokens(sentence)
            if overlap_tokens + sentence_tokens <= target_overlap_tokens:
                overlap_sentences.insert(0, sentence)
                overlap_tokens += sentence_tokens
            else:
                break

        return overlap_sentences if overlap_sentences else [sentences[-1]]
