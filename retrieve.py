"""
retrieve.py
Core RAG logic: embed a query, retrieve top-k chunks from ChromaDB, apply a
grounding gate (refuse if nothing relevant), and call Gemini to answer using
ONLY the retrieved excerpts, with inline citations.
"""

import re

import chromadb
from sentence_transformers import SentenceTransformer
from google import genai
from google.genai import errors
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential_jitter

from config import GEMINI_API_KEY, GEMINI_MODEL


GEMINI_CLIENT = genai.Client(api_key=GEMINI_API_KEY)

CHROMA_DIR = "data/chroma_db"
COLLECTION_NAME = "study_corpus"
EMBED_MODEL_NAME = "BAAI/bge-large-en-v1.5"

TOP_K = 8
# Chroma's default distance is cosine distance (lower = more similar) when
# using normalized embeddings. Tune this against your 10 "unanswerable"
# eval questions until they reliably fall above this threshold.
DISTANCE_REFUSAL_THRESHOLD = 0.55

REFUSAL_TEXT = (
    "My materials don't seem to cover this. I couldn't find anything in your "
    "documents that answers this confidently -- you may want to check other "
    "sources or ask your instructor."
)

TEMPORARY_API_ERROR_TEXT = (
    "Gemini is temporarily unavailable due to high demand. Please try your "
    "question again in a moment."
)

_embed_model = None
_client = None
_collection = None


def _get_resources():
    global _embed_model, _client, _collection
    if _embed_model is None:
        _embed_model = SentenceTransformer(EMBED_MODEL_NAME)
        _client = chromadb.PersistentClient(path=CHROMA_DIR)
        _collection = _client.get_collection(COLLECTION_NAME)
    return _embed_model, _collection


def retrieve_chunks(query: str, k: int = TOP_K):
    model, collection = _get_resources()
    query_emb = model.encode([f"query: {query}"], normalize_embeddings=True)[0].tolist()
    results = collection.query(query_embeddings=[query_emb], n_results=k)

    chunks = []
    for doc, meta, dist in zip(
        results["documents"][0], results["metadatas"][0], results["distances"][0]
    ):
        chunks.append({
            "text": doc,
            "doc_name": meta["doc_name"],
            "page_number": meta["page_number"],
            "image_path": meta["image_path"],
            "distance": dist,
        })
    return chunks


def build_prompt(question: str, chunks: list, history: list = None):
    excerpt_blocks = []
    for i, c in enumerate(chunks):
        excerpt_blocks.append(
            f"[{i + 1}] {c['doc_name']} p.{c['page_number']}:\n{c['text']}"
        )
    excerpts_text = "\n\n".join(excerpt_blocks)

    history_text = ""
    if history:
        turns = []
        for h in history[-5:]:  # last 5 turns for context
            turns.append(f"Q: {h['question']}\nA: {h['answer']}")
        history_text = "\n\nRecent conversation for context:\n" + "\n\n".join(turns)

    prompt = f"""You are a study assistant helping a student prepare for an exam.
Answer ONLY using the excerpts below. For every factual claim, cite it inline
using the format [DocName, p.N] exactly matching the document name and page
number shown in the excerpt headers.

If the excerpts do not contain enough information to answer confidently, say
explicitly: "My materials don't seem to cover this." Do not use outside
knowledge, do not guess, and do not fill gaps with plausible-sounding
information not present in the excerpts.

{history_text}

Excerpts:
{excerpts_text}

Question: {question}

Answer (with inline citations):"""
    return prompt


def extract_citations(answer_text: str):
    """Pull [DocName, p.N] style citations out of the answer text."""
    pattern = r"\[([^,\]]+),\s*p\.(\d+)\]"
    matches = re.findall(pattern, answer_text)
    return [{"doc_name": m[0].strip(), "page_number": int(m[1])} for m in matches]


def _is_retryable_api_error(exc: BaseException) -> bool:
    """Retry temporary Gemini service and rate-limit failures only."""
    return isinstance(exc, errors.APIError) and exc.code in {429, 500, 502, 503, 504}


@retry(
    retry=retry_if_exception(_is_retryable_api_error),
    wait=wait_exponential_jitter(initial=2, max=20),
    stop=stop_after_attempt(4),
    reraise=True,
)
def _generate_answer(prompt: str):
    return GEMINI_CLIENT.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
    )


def answer_question(question: str, history: list = None):
    chunks = retrieve_chunks(question)

    if not chunks or chunks[0]["distance"] > DISTANCE_REFUSAL_THRESHOLD:
        return {
            "answer": REFUSAL_TEXT,
            "citations": [],
            "chunks_used": [],
            "refused": True,
        }

    prompt = build_prompt(question, chunks, history)
    try:
        response = _generate_answer(prompt)
    except errors.APIError as exc:
        return {
            "answer": TEMPORARY_API_ERROR_TEXT,
            "citations": [],
            "chunks_used": chunks,
            "refused": False,
            "error": f"Gemini API {exc.code}: {exc.message}",
        }

    answer_text = response.text.strip()

    # Belt-and-suspenders: if the model itself declined, mark as refused too
    refused = "don't seem to cover this" in answer_text.lower() or "materials don't cover" in answer_text.lower()

    citations = extract_citations(answer_text)

    return {
        "answer": answer_text,
        "citations": citations,
        "chunks_used": chunks,
        "refused": refused,
        "error": None,
    }


if __name__ == "__main__":
    import sys
    q = " ".join(sys.argv[1:]) or "What is this course about?"
    result = answer_question(q)
    print("\n--- ANSWER ---")
    print(result["answer"])
    print("\n--- CITATIONS ---")
    for c in result["citations"]:
        print(c)
