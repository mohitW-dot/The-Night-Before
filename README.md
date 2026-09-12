# The Night Before

A study tool that answers only from your uploaded lecture PDFs, slides, notes,
and handwritten photos — with page-level citations, honest refusal when your
materials don't cover something, and persistent session memory so it behaves
like a study companion rather than a one-shot search box.

**100% free stack** — no paid APIs, no credit card required.


## What this does

Ask it a question about your course material, and it answers **only** from
the documents you gave it — with an inline citation to the exact document
and page, so you can go check it yourself. If your materials don't cover
something, it says so instead of guessing. Follow-up questions carry
context from the conversation, a sidebar tracks which pages you've actually
covered this session, and you can generate a quiz sourced strictly from
what you've discussed.

## Stack

| Layer | Tool | Cost |
|---|---|---|
| Answering / handwriting OCR / quiz generation | Gemini API (`gemini-3.6-flash`) | Free tier |
| Embeddings | Sentence Transformers (`bge-large-en-v1.5`), local | Free |
| Vector database | ChromaDB, local | Free |
| PDF parsing | PyMuPDF | Free |
| Slide parsing | python-pptx | Free |
| Session memory | SQLite | Free |
| UI | Streamlit | Free |

## Setup

1. Get a free Gemini API key at [aistudio.google.com](https://aistudio.google.com).
2. Clone this repo and install dependencies:
```bash
   python3 -m venv venv
   source venv/bin/activate   # Windows: venv\Scripts\activate
   pip install -r requirements.txt
```
3. Copy `.env.example` to `.env` and paste in your key:

GOOGLE_API_KEY=your-key-here

4. Drop your own course material into `corpus/`:
   - `corpus/pdfs/` — lecture PDFs
   - `corpus/slides/` — .pptx decks
   - `corpus/notes/` — .md or .txt files
   - `corpus/handwritten/` — photos of handwritten pages (.jpg/.png)

## Build the index

```bash
python ingest.py     # extracts text + transcribes handwritten photos via Gemini vision
python index.py      # chunks + embeds locally + writes to ChromaDB
```

After `ingest.py` runs, **manually skim `data/chunks.json`**, especially the
`"doc_type": "handwritten"` entries, to sanity-check transcription quality
before indexing.

## Run the app

```bash
streamlit run app.py
```

## Run the evaluation

1. Fill in your 30 hand-labeled questions in `eval/questions.json`
   (10 single-document, 10 cross-document, 10 unanswerable), recording the
   correct source page for each by hand.
2. Run:
```bash
   python eval.py
```
3. Results and a scorecard are written to `eval/results.json` and printed to
   console.

### Scorecard

- Correct with source: **16 / 20**
- Correctly refused: **8 / 10**


## 🏗️ Architecture

```text
                         ┌─────────────────────────┐
                         │       corpus/           │
                         │                         │
                         │ PDFs / Slides / Notes   │
                         │ Handwritten Photos      │
                         └────────────┬────────────┘
                                      │
                                      ▼
                              ┌───────────────┐
                              │   ingest.py   │
                              │               │
                              │ Text + OCR +  │
                              │ descriptions  │
                              └───────┬───────┘
                                      │
                                      ▼
                              ┌────────────────┐
                              │ data/          │
                              │ chunks.json    │
                              └───────┬────────┘
                                      │
                                      ▼
                              ┌───────────────┐
                              │   index.py    │
                              │               │
                              │ Local BGE     │
                              │ embeddings    │
                              └───────┬───────┘
                                      │
                                      ▼
                              ┌────────────────┐
                              │ data/chroma_db │
                              │ Vector Store   │
                              └───────┬────────┘
                                      │
                                      ▼
                              ┌───────────────┐
                              │  retrieve.py  │
                              └───────┬───────┘
                                      │
                         ┌────────────┴────────────┐
                         │                         │
                         ▼                         ▼
                  ┌──────────────┐          ┌──────────────┐
                  │    app.py    │          │  memory.py   │
                  │  Streamlit   │          │    SQLite    │
                  │     UI       │          │    Memory    │
                  └──────┬───────┘          └──────┬───────┘
                         │                         │
                         └────────────┬────────────┘
                                      │
                                      ▼
                              ┌───────────────┐
                              │  Gemini API   │
                              │ Grounded LLM  │
                              └───────┬───────┘
                                      │
                                      ▼
                           ┌────────────────────┐
                           │ Answer + Citations │
                           │ Grounded Quiz      │
                           └─────────┬──────────┘
                                     │
                                     ▼
                              ┌──────────────┐
                              │   eval.py    │
                              └──────┬───────┘
                                     │
                                     ▼
                            ┌──────────────────┐
                            │ eval/results.json│
                            │    Scorecard     │
                            └──────────────────┘
```

## What's beyond the floor

- **Persistent session memory** (`memory.py`, SQLite) — follow-up questions
  resolve using recent conversation context, not just the current message.
- **Coverage tracker** (sidebar) — shows which document pages have actually
  been discussed this session, surfacing untouched material.
- **Grounded quiz generation** — generates practice questions strictly from
  material cited in your recent answers, not generic trivia.
- **Handwriting transparency** — any answer citing a handwritten page shows
  both the Gemini transcription and the original photo, so you can judge
  transcription quality yourself rather than trust it blindly.

## Known limitations

- Handwriting transcription quality depends on photo clarity — the
  deliberately hard-to-read scan in this corpus is included to demonstrate
  this honestly rather than hide it. Uncertain words are marked
  `[unclear: ...]` in the transcription rather than silently guessed.
- Gemini's free tier has per-minute rate limits; `ingest.py` includes short
  sleeps between vision calls to stay under them.
- The refusal threshold (`DISTANCE_REFUSAL_THRESHOLD` in `retrieve.py`) is
  tuned against this project's own eval set — a very different corpus may
  need it adjusted.
