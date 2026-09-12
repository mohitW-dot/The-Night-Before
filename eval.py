"""
eval.py
Runs the hand-labeled question set (eval/questions.json) through the RAG
pipeline and scores it:
  - For the 20 answerable questions: was the correct source page cited?
  - For the 10 unanswerable questions: did it correctly refuse?

Run:  python eval.py
"""

import json
from pathlib import Path

from retrieve import answer_question

QUESTIONS_PATH = Path("eval/questions.json")
RESULTS_PATH = Path("eval/results.json")


def write_results(summary, results):
    """Persist completed work after every question so an interrupted run is useful."""
    RESULTS_PATH.write_text(json.dumps({"summary": summary, "details": results}, indent=2))


def page_match(citations, expected_doc, expected_page):
    return any(
        expected_doc.lower() in c["doc_name"].lower() and c["page_number"] == expected_page
        for c in citations
    )


def cross_doc_match(citations, expected_docs_pages):
    """expected_docs_pages: list of 'DocName p.N' strings"""
    hits = 0
    for expected in expected_docs_pages:
        doc_part, page_part = expected.rsplit(" p.", 1)
        expected_page = int(page_part)
        if page_match(citations, doc_part, expected_page):
            hits += 1
    return hits >= 2  # require at least 2 of the combined sources to be cited


def main():
    questions = json.loads(QUESTIONS_PATH.read_text())
    results = []

    correct_with_source = 0
    correctly_refused = 0
    total_answerable = 0
    total_unanswerable = 0
    api_errors = 0

    for q in questions:
        print(f"Q{q['id']}: {q['question'][:70]}...")
        result = answer_question(q["question"])

        entry = {
            "id": q["id"],
            "question": q["question"],
            "type": q["type"],
            "model_answer": result["answer"],
            "model_citations": result["citations"],
            "refused": result["refused"],
            "error": result.get("error"),
        }

        if result.get("error"):
            api_errors += 1
            entry["correct"] = False
            print(f"    skipped: {result['error']}")

        elif q["type"] == "unanswerable":
            total_unanswerable += 1
            if result["refused"]:
                correctly_refused += 1
                entry["correct"] = True
            else:
                entry["correct"] = False

        elif q["type"] == "single_doc":
            total_answerable += 1
            is_correct = (not result["refused"]) and page_match(
                result["citations"], q["expected_doc"], q["expected_page"]
            )
            entry["correct"] = is_correct
            if is_correct:
                correct_with_source += 1

        elif q["type"] == "cross_doc":
            total_answerable += 1
            is_correct = (not result["refused"]) and cross_doc_match(
                result["citations"], q["expected_docs"]
            )
            entry["correct"] = is_correct
            if is_correct:
                correct_with_source += 1

        results.append(entry)
        if not result.get("error"):
            print(f"    correct: {entry['correct']}")

        summary = {
            "correct_with_source": correct_with_source,
            "total_answerable": total_answerable,
            "correctly_refused": correctly_refused,
            "total_unanswerable": total_unanswerable,
            "api_errors": api_errors,
        }
        write_results(summary, results)

    summary = {
        "correct_with_source": correct_with_source,
        "total_answerable": total_answerable,
        "correctly_refused": correctly_refused,
        "total_unanswerable": total_unanswerable,
        "api_errors": api_errors,
    }

    write_results(summary, results)

    print("\n===== SCORECARD =====")
    print(f"Correct with source: {correct_with_source}/{total_answerable}")
    print(f"Correctly refused:   {correctly_refused}/{total_unanswerable}")
    print(f"Temporary API errors: {api_errors}")
    print(f"Full results written to {RESULTS_PATH}")


if __name__ == "__main__":
    main()
