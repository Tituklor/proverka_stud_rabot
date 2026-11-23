import numpy as np


def find_matches(vectors, shingle_sets, storage, before_seq, settings):

    ref_matrix, ref_meta = storage.load_vectors(before_seq)
    if not ref_meta:
        return {}, [], False

    row_of = {m["fragment_id"]: j for j, m in enumerate(ref_meta)}
    sims = vectors @ ref_matrix.T
    matches, best_similarity = {}, []

    for i in range(len(vectors)):
        best_j = int(np.argmax(sims[i]))
        best_cos = float(sims[i][best_j])
        best_similarity.append(round(best_cos, 3))

        n_shingles = len(shingle_sets[i])
        counts = storage.shingle_overlap(shingle_sets[i], before_seq) if n_shingles else {}

        if counts:
            frag_id, shared = max(counts.items(), key=lambda kv: kv[1])
            ratio = shared / n_shingles
            if ratio >= settings["shingle_threshold"]:
                j = row_of[frag_id]
                matches[i] = _describe("exact", ref_meta[j], float(sims[i][j]), ratio)
                continue

        if best_cos >= settings["semantic_threshold"]:
            ref = ref_meta[best_j]
            ratio = counts.get(ref["fragment_id"], 0) / n_shingles if n_shingles else 0.0
            matches[i] = _describe("semantic", ref, best_cos, ratio)

    return matches, best_similarity, True


def _describe(kind, ref, cosine, shingle_ratio):
    return {
        "kind": kind,                         
        "source_work_id": ref["work_id"],
        "source_fragment": ref["text"],
        "similarity": round(cosine, 3),
        "shingle_overlap": round(shingle_ratio, 3),
    }
