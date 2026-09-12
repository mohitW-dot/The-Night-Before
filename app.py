"""
app.py
Streamlit UI for the study assistant.

Run:  streamlit run app.py
"""

import json
from pathlib import Path

import streamlit as st
from google import genai

from config import GEMINI_API_KEY, GEMINI_MODEL
from retrieve import answer_question
import memory

GEMINI_CLIENT = genai.Client(api_key=GEMINI_API_KEY)

memory.init_db()

st.set_page_config(page_title="Study Assistant", layout="wide")

# ---------------------------------------------------------------- sidebar --
with st.sidebar:
    st.header("Session")

    if st.button("Clear session memory"):
        memory.clear_session()
        st.rerun()

    st.subheader("Coverage this session")
    covered = memory.get_covered_pages()
    if covered:
        by_doc = {}
        for doc_name, page in covered:
            by_doc.setdefault(doc_name, []).append(page)
        for doc_name, pages in by_doc.items():
            st.caption(f"**{doc_name}**: p. {', '.join(str(p) for p in sorted(pages))}")
    else:
        st.caption("Nothing covered yet -- ask a question to get started.")

    st.divider()
    st.subheader("Quiz me")
    st.caption("Generates questions strictly from material cited in your recent answers.")
    if st.button("Generate quiz from this session"):
        recent_citations = memory.get_recently_cited_chunks(n_turns=4)
        if not recent_citations:
            st.warning("Ask a few grounded questions first, then generate a quiz.")
        else:
            citation_summary = "\n".join(
                f"- {c['doc_name']} p.{c['page_number']}" for c in recent_citations
            )
            recent_log = memory.get_recent_history(n=4)
            context_text = "\n\n".join(
                f"Q: {t['question']}\nA: {t['answer']}" for t in recent_log
            )
            quiz_prompt = f"""Based ONLY on the following question-and-answer exchanges
(which are grounded in the student's own course material), generate 3 multiple
choice questions to help them practice. Each question should have 4 options,
one correct answer, and cite the source page it comes from using the
exact format [DocName, p.N].

Recent exchanges:
{context_text}

Return the quiz as plain text, one question at a time, formatted clearly."""
            with st.spinner("Generating quiz from your session..."):
                quiz_response = GEMINI_CLIENT.models.generate_content(
                    model=GEMINI_MODEL,
                    contents=quiz_prompt,
                )
            st.session_state["quiz_text"] = quiz_response.text

    if "quiz_text" in st.session_state:
        st.markdown("### Your quiz")
        st.markdown(st.session_state["quiz_text"])

# ------------------------------------------------------------- main chat --
st.title("Study Assistant")
st.caption("Answers only from your uploaded course material, with page-level citations. Says so when it doesn't know.")

# Render existing history
log = memory.get_full_log()
for turn in log:
    with st.chat_message("user"):
        st.write(turn["question"])
    with st.chat_message("assistant"):
        if turn["refused"]:
            st.warning(turn["answer"])
        else:
            st.write(turn["answer"])
            citations = json.loads(turn["citations"])
            if citations:
                with st.expander(f"Sources ({len(citations)})"):
                    for c in citations:
                        st.caption(f"{c['doc_name']}, p.{c['page_number']}")

# New question
question = st.chat_input("Ask about your course material...")
if question:
    with st.chat_message("user"):
        st.write(question)

    history = memory.get_recent_history(n=5)

    with st.chat_message("assistant"):
        with st.spinner("Searching your materials..."):
            result = answer_question(question, history=history)

        if result.get("error"):
            st.error(result["answer"])
        elif result["refused"]:
            st.warning(result["answer"])
        else:
            st.write(result["answer"])

            if result["citations"]:
                with st.expander(f"Sources ({len(result['citations'])})"):
                    # Match citations back to chunks_used to find image paths
                    for cite in result["citations"]:
                        matched_chunk = next(
                            (c for c in result["chunks_used"]
                             if c["doc_name"] == cite["doc_name"]
                             and c["page_number"] == cite["page_number"]),
                            None,
                        )
                        st.caption(f"**{cite['doc_name']}, p.{cite['page_number']}**")
                        if matched_chunk and matched_chunk.get("image_path"):
                            img_path = Path(matched_chunk["image_path"])
                            if img_path.exists():
                                st.image(str(img_path), width=400)
                        if matched_chunk:
                            st.text(matched_chunk["text"][:500])
                        st.divider()

    if not result.get("error"):
        memory.log_turn(
            question=question,
            answer=result["answer"],
            citations=result["citations"],
            refused=result["refused"],
        )
    st.rerun()
