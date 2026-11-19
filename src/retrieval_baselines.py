"""Matched lexical baselines; fit vocabulary and IDF on registry documents only."""

from collections import Counter
import math

try:
    from .evidence import tokens, retrieve
    from .confirmation import overlap_retrieve
except ImportError:
    from evidence import tokens, retrieve
    from confirmation import overlap_retrieve


def tfidf_retrieve(question, registry, k=3):
    """Raw document TF, binary query TF, smoothed IDF and cosine normalization.

    IDF = 1 + ln((N+1)/(df+1)); query OOV terms are discarded. Both vectors
    use this IDF. Fields, stopwords, positive-score filtering and ties match
    the existing retrievers. Scores are relevance weights, not probabilities.
    """
    if not isinstance(k, int) or isinstance(k, bool) or k < 1:
        raise ValueError("Positive integer k required")
    documents = registry["documents"]
    counts = [Counter(tokens(d["title"] + " " + d["text"])) for d in documents]
    df = Counter(word for count in counts for word in count)
    idf = {word: 1 + math.log((len(documents) + 1) / (freq + 1))
           for word, freq in df.items()}
    query = {word: idf[word] for word in sorted(set(tokens(question))) if word in idf}
    qnorm = math.sqrt(sum(weight * weight for weight in query.values()))
    if not qnorm:
        return []
    hits = []
    for document, count in zip(documents, counts):
        norm = math.sqrt(sum((freq * idf[word]) ** 2 for word, freq in sorted(count.items())))
        dot = sum(weight * count[word] * idf[word] for word, weight in query.items())
        if dot > 0 and norm:
            hits.append({**document, "score": dot / (qnorm * norm)})
    return sorted(hits, key=lambda d: (-d["score"], d["id"]))[:k]


METHODS = {"bm25": retrieve, "tfidf": tfidf_retrieve, "keyword_overlap": overlap_retrieve}
