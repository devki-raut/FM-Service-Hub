from __future__ import annotations

import asyncio
import re
from collections import Counter
from pathlib import Path
from typing import Iterable

import fitz
import streamlit as st

from app.excel_agent import try_answer_excel_question
from app.models import ChatRequest, ChatResponse, ImageReference, Source
from app.rag import RagService
from app.rag_constants import MISSING_DATA_ANSWER
from app.visuals import images_for_question


APP_TITLE = "FM Service Hub"
DOC_ROOT = Path("FM SERVICE HUB")
SAMPLE_PROMPTS = [
    "What is the overall count of complaints for CX2000 for 2025?",
    "Count complaints by branch for 2025.",
    "Show the wall mounting / bracket installation diagram for CX2000.",
    "Show the CX2000 internal layout diagram.",
]
STOPWORDS = {
    "about",
    "after",
    "and",
    "answer",
    "are",
    "can",
    "count",
    "data",
    "does",
    "for",
    "from",
    "give",
    "how",
    "many",
    "overall",
    "please",
    "show",
    "the",
    "this",
    "total",
    "what",
    "when",
    "where",
    "which",
    "with",
}


st.set_page_config(
    page_title=APP_TITLE,
    layout="wide",
    initial_sidebar_state="collapsed",
)


def main() -> None:
    _load_styles()
    _init_state()

    with st.sidebar:
        _sidebar()

    _header()
    _prompt_bar()
    _chat_panel()


def _init_state() -> None:
    st.session_state.setdefault(
        "messages",
        [
            {
                "role": "assistant",
                "content": (
                    "Ask me about CX2000 procedures, manuals, diagrams, or complaint analytics. "
                    "I will give a concise answer for your workflow."
                ),
                "response": None,
                "error": None,
            }
        ],
    )
    st.session_state.setdefault("pending_prompt", "")


def _sidebar() -> None:
    st.markdown("### Conversation")
    if st.button("Clear conversation", use_container_width=True):
        st.session_state["messages"] = []
        st.rerun()


def _header() -> None:
    st.markdown(
        """
        <section class="hero">
          <div>
            <p class="eyebrow">AI assistant workspace</p>
            <h1>FM Service Hub</h1>
            <p class="subhead">
              A focused assistant for RFQ, CX2000 manual, training, and complaints intelligence.
            </p>
          </div>
        </section>
        """,
        unsafe_allow_html=True,
    )



def _prompt_bar() -> None:
    st.markdown("### Try a Scenario")
    cols = st.columns(4)
    for col, prompt in zip(cols, SAMPLE_PROMPTS):
        if col.button(prompt, use_container_width=True):
            st.session_state["pending_prompt"] = prompt


def _chat_panel() -> None:
    for message in st.session_state["messages"]:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if message.get("response"):
                _render_response_details(message["response"])
            if message.get("error"):
                st.error(message["error"])

    prompt = st.chat_input("Ask a question")
    if not prompt and st.session_state["pending_prompt"]:
        prompt = st.session_state.pop("pending_prompt")
    if not prompt:
        return

    st.session_state["messages"].append({"role": "user", "content": prompt, "response": None, "error": None})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Preparing answer..."):
            response, error = _answer(prompt)
        if error:
            st.error(error)
            content = "I could not complete that request right now."
        else:
            content = response.answer
            st.markdown(content)
            _render_response_details(response)
        st.session_state["messages"].append(
            {"role": "assistant", "content": content, "response": response if not error else None, "error": error}
        )


def _answer(question: str) -> tuple[ChatResponse, str | None]:
    try:
        return _run_live_rag(question), None
    except Exception:
        return _demo_answer(question), None


def _run_live_rag(question: str) -> ChatResponse:
    return asyncio.run(RagService().answer(ChatRequest(question=question)))


def _demo_answer(question: str) -> ChatResponse:
    excel_response = try_answer_excel_question(question)
    if excel_response is not None:
        return excel_response

    sources = _local_pdf_sources(question)
    if not sources:
        return ChatResponse(answer=MISSING_DATA_ANSWER, sources=[])

    answer = _extractive_answer(question, sources)
    images = images_for_question(question, sources)
    return ChatResponse(answer=answer, sources=sources, images=images)


@st.cache_data(show_spinner=False)
def _knowledge_files() -> list[Path]:
    roots = [Path("."), DOC_ROOT]
    files = []
    for root in roots:
        if not root.exists():
            continue
        for path in root.iterdir():
            if path.suffix.casefold() in {".pdf", ".pptx", ".xlsx", ".xls", ".csv"} and not path.name.startswith("~$"):
                files.append(path)
    return sorted(set(files), key=lambda item: item.name.casefold())


@st.cache_data(show_spinner=False)
def _pdf_pages() -> list[dict]:
    pages = []
    for path in _knowledge_files():
        if path.suffix.casefold() != ".pdf":
            continue
        try:
            with fitz.open(path) as document:
                for index, page in enumerate(document, start=1):
                    text = " ".join(page.get_text("text").split())
                    if len(text) >= 80:
                        pages.append({"path": path, "page": index, "text": text})
        except Exception:
            continue
    return pages


def _local_pdf_sources(question: str, limit: int = 4) -> list[Source]:
    query_terms = _tokens(question)
    scored = []
    for page in _pdf_pages():
        text_terms = set(_tokens(page["text"]))
        overlap = len(set(query_terms) & text_terms)
        phrase_bonus = _phrase_bonus(question, page["text"])
        score = overlap + phrase_bonus
        if score > 0:
            scored.append((score, page))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [
        Source(
            document_name=page["path"].name,
            page=page["page"],
            section="Local demo excerpt",
            score=float(score),
            content=_trim_excerpt(page["text"], question),
        )
        for score, page in scored[:limit]
    ]


def _extractive_answer(question: str, sources: list[Source]) -> str:
    sentences = []
    query_terms = set(_tokens(question))
    for source in sources:
        for sentence in re.split(r"(?<=[.!?])\s+", source.content):
            if len(sentence) < 30:
                continue
            sentence_terms = set(_tokens(sentence))
            if query_terms & sentence_terms:
                sentences.append(sentence.strip())
            if len(sentences) >= 3:
                break
        if len(sentences) >= 3:
            break
    if not sentences:
        return sources[0].content[:700].strip()
    return " ".join(sentences)


def _render_response_details(response: ChatResponse) -> None:
    if response.images:
        st.markdown("#### Visual Evidence")
        image_cols = st.columns(min(len(response.images), 2))
        for col, image in zip(image_cols, response.images):
            with col:
                _render_image(image)


def _render_image(image: ImageReference) -> None:
    source = image.data_url or image.url
    st.image(source, caption=image.caption or f"{image.document_name}, page {image.page}")


def _tokens(text: str) -> list[str]:
    return [token for token in re.findall(r"[a-z0-9]+", text.casefold()) if len(token) >= 3 and token not in STOPWORDS]


def _phrase_bonus(question: str, text: str) -> int:
    normalized_text = text.casefold()
    phrases = _important_phrases(question)
    return sum(3 for phrase in phrases if phrase in normalized_text)


def _important_phrases(question: str) -> Iterable[str]:
    words = _tokens(question)
    counts = Counter(words)
    for word, _ in counts.most_common(8):
        yield word
    for first, second in zip(words, words[1:]):
        yield f"{first} {second}"


def _trim_excerpt(text: str, question: str, window: int = 950) -> str:
    terms = _tokens(question)
    lowered = text.casefold()
    positions = [lowered.find(term) for term in terms if lowered.find(term) >= 0]
    if not positions:
        return text[:window]
    midpoint = min(positions)
    start = max(0, midpoint - window // 3)
    end = min(len(text), start + window)
    return text[start:end].strip()


def _load_styles() -> None:
    st.markdown(
        """
        <style>
        .stApp {
            background: #f6f7f9;
            color: #18202a;
        }
        .hero {
            align-items: center;
            background: linear-gradient(135deg, #113b5f 0%, #245f73 50%, #f2b84b 100%);
            border-radius: 8px;
            color: white;
            display: flex;
            justify-content: space-between;
            margin-bottom: 1rem;
            min-height: 210px;
            overflow: hidden;
            padding: 2rem;
        }
        .hero h1 {
            font-size: 3rem;
            letter-spacing: 0;
            line-height: 1.05;
            margin: 0;
        }
        .eyebrow {
            font-size: .82rem;
            font-weight: 700;
            letter-spacing: 0;
            margin-bottom: .35rem;
            text-transform: uppercase;
        }
        .subhead {
            font-size: 1.05rem;
            margin-top: .8rem;
            max-width: 720px;
        }
        .stButton button {
            border-radius: 8px;
            min-height: 3rem;
            white-space: normal;
        }
        @media (max-width: 780px) {
            .hero {
                align-items: flex-start;
                flex-direction: column;
                gap: 1rem;
                padding: 1.25rem;
            }
            .hero h1 {
                font-size: 2.2rem;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

if __name__ == "__main__":
    main()
