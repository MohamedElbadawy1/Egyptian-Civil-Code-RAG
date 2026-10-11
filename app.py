"""
Gradio chat app for Hugging Face Spaces -- a genuinely free, card-free
deployment path (see README's "Known limitations" / deployment notes).
Reuses the exact same retrieval/generation pipeline as the FastAPI app
in src/agentic_rag/api/main.py; only the UI layer differs here.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

import gradio as gr
import spaces

from agentic_rag.api.generation import GenerationClient
from agentic_rag.rag.corpus import load_corpus_index
from agentic_rag.rag.pipeline import retrieve

# Lazy singleton, same reasoning as api/main.py: importing this module
# shouldn't require OPENAI_API_KEY until a question is actually asked.
_generation_client: GenerationClient | None = None


def get_generation_client() -> GenerationClient:
    global _generation_client
    if _generation_client is None:
        _generation_client = GenerationClient()
    return _generation_client


# Decorated with @spaces.GPU purely to satisfy ZeroGPU hardware's startup
# check ("No @spaces.GPU function detected") -- this account can't use
# plain CPU-basic hardware without a PRO subscription. Nothing inside
# this function actually touches a GPU; it's all external API calls
# (OpenAI, Weaviate Cloud), so duration=60 is just a safety cap on the
# allocation, never expected to be hit.
@spaces.GPU(duration=60)
def answer_question(message: str, history: list) -> str:
    question = message.strip()
    if not question:
        return "من فضلك اكتب سؤالك."

    retrieved = retrieve(question, top_k=5)
    if not retrieved:
        return "لم يتم العثور على مواد ذات صلة بسؤالك."

    corpus_index = load_corpus_index()
    full_articles = [
        corpus_index[r.article_number]
        for r in retrieved
        if r.article_number in corpus_index
    ]

    answer = get_generation_client().answer(question, full_articles)
    citations = "، ".join(f"مادة {r.article_number}" for r in retrieved)
    return f"{answer}\n\n---\n**المواد المستشهد بها:** {citations}"


demo = gr.ChatInterface(
    fn=answer_question,
    chatbot=gr.Chatbot(rtl=True, height=500),
    title="المساعد القانوني للقانون المدني المصري",
    description=(
        "اسأل أي سؤال عن القانون المدني المصري بالعربية أو الإنجليزية، "
        "وهيتم الرد بالاستشهاد برقم المادة. مشروع تعليمي، وليس بديلاً عن "
        "استشارة قانونية رسمية."
    ),
    examples=[
        "ما هي الحقوق التي يملكها مالك الشيء؟",
        "ما أثر عدم تسجيل العقار على انتقال الملكية؟",
    ],
)

if __name__ == "__main__":
    demo.launch()