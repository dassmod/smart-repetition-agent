"""
Vault semantic retrieval - Rung 3.

Reads every lesson's real markdown content from the vault, cuts it into
paragraph-sized chunks, embeds each chunk, and stores the embeddings next
to their text so we can later search by meaning (cosine similarity) or
look up a lesson's full content by name.

Nothing here is hidden inside a library: chunk, embed, store, and search
are four plain steps you can read top to bottom.
"""

import json
from pathlib import Path

import numpy as np

from agent.src.retrieval.embedder import embed_texts, embed_query

CHUNK_TARGET_WORDS = 200


def strip_frontmatter(raw_text: str) -> str:
    """Remove a leading YAML frontmatter block (between --- markers), if present."""
    if raw_text.startswith('---'):
        parts = raw_text.split('---', 2)
        if len(parts) >= 3:
            return parts[2].strip()
    return raw_text


def chunk_content(body: str, target_words: int = CHUNK_TARGET_WORDS) -> list[str]:
    """
    Split lesson content into paragraph-aligned chunks of roughly target_words each.

    Paragraphs (separated by blank lines) are never split mid-way; they are
    greedily packed together until adding the next one would cross the target.
    """
    paragraphs = [p.strip() for p in body.split("\n\n") if p.strip()]

    chunks: list[str] = []
    current: list[str] = []
    current_words = 0

    for paragraph in paragraphs:
        paragraph_words = len(paragraph.split())
        if current and current_words + paragraph_words > target_words:
            chunks.append("\n\n".join(current))
            current = []
            current_words = 0
        current.append(paragraph)
        current_words += paragraph_words

    if current:
        chunks.append("\n\n".join(current))

    return chunks


class VaultIndex:
    """Chunk-level embeddings for search-by-meaning, plus full lesson text for exact lookup."""

    def __init__(self) -> None:
        self.chunks: list[dict] = []          # each: text, lesson_name, chapter, course, chunk_index
        self.embeddings: np.ndarray | None = None
        self.lesson_content: dict[str, str] = {}  # lesson_name -> full body text

    def build(self, courses_json_path: str) -> None:
        """Read every lesson's real file, chunk it, and embed all chunks in one batch."""
        with open(courses_json_path, 'r', encoding='utf-8') as f:
            courses = json.load(f)

        all_texts: list[str] = []

        for course in courses:
            for chapter in course['chapters']:
                for lesson in chapter['lessons']:
                    raw = Path(lesson['file_path']).read_text(encoding='utf-8')
                    body = strip_frontmatter(raw)
                    self.lesson_content[lesson['name']] = body

                    for i, chunk_text in enumerate(chunk_content(body)):
                        self.chunks.append({
                            "text": chunk_text,
                            "lesson_name": lesson['name'],
                            "chapter": chapter['name'],
                            "course": course['title'],
                            "chunk_index": i,
                        })
                        all_texts.append(chunk_text)

        self.embeddings = embed_texts(all_texts)

    def save(self, dir_path: str) -> None:
        out_dir = Path(dir_path)
        out_dir.mkdir(parents=True, exist_ok=True)
        np.save(out_dir / "embeddings.npy", self.embeddings)
        with open(out_dir / "chunks.json", 'w', encoding='utf-8') as f:
            json.dump(
                {"chunks": self.chunks, "lesson_content": self.lesson_content},
                f,
            )

    def load(self, dir_path: str) -> bool:
        """Load a previously saved index. Returns False if no saved index exists yet."""
        out_dir = Path(dir_path)
        embeddings_path = out_dir / "embeddings.npy"
        chunks_path = out_dir / "chunks.json"
        if not embeddings_path.exists() or not chunks_path.exists():
            return False

        self.embeddings = np.load(embeddings_path)
        with open(chunks_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        self.chunks = data["chunks"]
        self.lesson_content = data["lesson_content"]
        return True

    def search(self, query: str, k: int = 5) -> list[dict]:
        """Find the k chunks whose meaning is closest to the query."""
        query_vec = embed_query(query)

        # cosine similarity between the query and every stored chunk, at once
        norms = np.linalg.norm(self.embeddings, axis=1) * np.linalg.norm(query_vec)
        similarities = (self.embeddings @ query_vec) / norms

        top_indices = np.argsort(-similarities)[:k]

        results = []
        for i in top_indices:
            result = dict(self.chunks[i])
            result["score"] = float(similarities[i])
            results.append(result)
        return results

    def get_lesson_content(self, lesson_name: str) -> str:
        """Exact lookup of a lesson's full body text by name."""
        return self.lesson_content.get(lesson_name, "")


def load_or_build(index_dir: str, courses_json_path: str) -> VaultIndex:
    """Load the saved index if one exists, otherwise build it from the vault and save it."""
    index = VaultIndex()
    if not index.load(index_dir):
        index.build(courses_json_path)
        index.save(index_dir)
    return index
