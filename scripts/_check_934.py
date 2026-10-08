from agentic_rag.rag.pipeline import retrieve

results = retrieve(
    "ما أثر عدم تسجيل العقار على انتقال الملكية؟",
    top_k=20,
    use_hybrid=True,
)
for r in results:
    marker = "  <== HERE" if r.article_number == 934 else ""
    print(r.article_number, round(r.score, 3), marker)