"""
index.py
Loads data/chunks.json, splits long pages into sub-chunks (keeping page/doc
metadata attached), embeds with a local Sentence Transformers model, and
upserts into a persistent ChromaDB collection.

Run:  python index.py
"""

import json
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer

CHUNKS_PATH = Path("data/chunks.json")
CHROMA_DIR = "data/chroma_db"
COLLECTION_NAME = "study_corpus"

# Good quality/size tradeoff. Swap to "all-MiniLM-L6-v2" for a much smaller/
# faster (but slightly less accurate) local model.
EMBED_MODEL_NAME = "BAAI/bge-large-en-v1.5"

MAX_CHUNK_CHARS = 2200  # ~roughly 500-600 tokens
OVERLAP_CHARS = 200


def split_text(text: str):
    """Simple sliding-window splitter for long pages."""
    if len(text) <= MAX_CHUNK_CHARS:
        return [text]
    chunks = []
    start = 0
    while start < len(text):
        end = start + MAX_CHUNK_CHARS
        chunks.append(text[start:end])
        start = end - OVERLAP_CHARS
    return chunks


def main():
    records = json.loads(CHUNKS_PATH.read_text(encoding="utf-8"))
    print(f"Loaded {len(records)} page/section records")

    print(f"Loading embedding model: {EMBED_MODEL_NAME} (first run downloads weights)")
    model = SentenceTransformer(EMBED_MODEL_NAME)

    client = chromadb.PersistentClient(path=CHROMA_DIR)
    # Fresh collection each run -- simplest for a small, iterative project
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass
    collection = client.create_collection(COLLECTION_NAME)

    ids, texts, metadatas = [], [], []
    for rec in records:
        sub_chunks = split_text(rec["text"])
        for j, sub_text in enumerate(sub_chunks):
            chunk_id = f"{rec['doc_id']}_p{rec['page_number']}_c{j}"
            ids.append(chunk_id)
            texts.append(sub_text)
            metadatas.append({
                "doc_name": rec["doc_name"],
                "doc_type": rec["doc_type"],
                "page_number": rec["page_number"],
                "image_path": rec["image_path"] or "",
            })

    print(f"Embedding {len(texts)} chunks locally ...")
    # bge models recommend a query/passage prefix for best retrieval quality
    prefixed_texts = [f"passage: {t}" for t in texts]
    embeddings = model.encode(prefixed_texts, show_progress_bar=True, normalize_embeddings=True)

    print("Writing to ChromaDB ...")
    collection.add(
        ids=ids,
        embeddings=embeddings.tolist(),
        documents=texts,
        metadatas=metadatas,
    )

    print(f"Done. Indexed {len(texts)} chunks into '{COLLECTION_NAME}' at {CHROMA_DIR}")


if __name__ == "__main__":
    main()
