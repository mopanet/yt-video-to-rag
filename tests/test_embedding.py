import threading
import time

import numpy as np
import pytest
from helpers import FakeEmbedder

from video_to_rag.captions import Segment
from video_to_rag.chunking import chunk
from video_to_rag.embedding import (
    MODEL_DIM,
    MODEL_NAME,
    E5Embedder,
    Embedder,
    EmbeddingUnavailable,
    model_cache_dir,
)


def test_fake_embedder_satisfies_the_protocol():
    assert isinstance(FakeEmbedder(), Embedder)


def test_fake_embedder_is_stable_and_normalized():
    texts = ["how to improve focus", "cold exposure and dopamine", ""]
    first = FakeEmbedder().embed_passages(texts)
    again = FakeEmbedder().embed_queries(texts)
    assert first.shape == (3, 64)
    np.testing.assert_array_equal(first, again)
    np.testing.assert_allclose(np.linalg.norm(first, axis=1), 1.0, rtol=1e-6)
    assert not np.allclose(first[0], first[1])


def test_fake_embedder_empty_batch():
    assert FakeEmbedder().embed_passages([]).shape == (0, 64)


def test_model_cache_lives_in_the_user_cache_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    assert model_cache_dir() == tmp_path / "video-to-rag" / "models"


def test_e5_announces_the_first_download(tmp_path, caplog, monkeypatch):
    loaded = []

    class FakeTextEmbedding:
        def __init__(self, model_name, **kwargs):
            loaded.append((model_name, kwargs["cache_dir"]))

    monkeypatch.setattr("fastembed.TextEmbedding", FakeTextEmbedding)
    with caplog.at_level("INFO", logger="video_to_rag"):
        E5Embedder(cache_dir=tmp_path)._load()
    assert loaded == [(MODEL_NAME, str(tmp_path))]
    assert "2.2 GB" in caplog.text


def test_e5_prefixes_and_normalizes(tmp_path, monkeypatch):
    seen = []

    class FakeTextEmbedding:
        def __init__(self, model_name, **kwargs):
            pass

        def embed(self, texts, **kwargs):
            seen.extend(texts)
            three_four = np.zeros(MODEL_DIM, np.float32)
            three_four[:2] = [3.0, 4.0]
            return [three_four, np.zeros(MODEL_DIM, np.float32)][: len(texts)]

    monkeypatch.setattr("fastembed.TextEmbedding", FakeTextEmbedding)
    e5 = E5Embedder(cache_dir=tmp_path)
    assert e5.embed_passages([]).shape == (0, MODEL_DIM)
    queries = e5.embed_queries(["focus", "x"])
    e5.embed_passages(["text"])
    assert seen == ["query: focus", "query: x", "passage: text"]
    np.testing.assert_allclose(queries[0][:2], [0.6, 0.8])
    assert not np.isnan(queries).any()  # a zero vector stays zero, never NaN


def test_e5_embeds_in_small_batches(tmp_path, monkeypatch):
    # fastembed's default batch of 256 pads a whole long video into one ONNX run (OOM).
    batch_sizes = []

    class FakeTextEmbedding:
        def __init__(self, model_name, **kwargs):
            pass

        def embed(self, texts, batch_size=256, **kwargs):
            batch_sizes.append(batch_size)
            return [np.ones(MODEL_DIM, np.float32) for _ in texts]

    monkeypatch.setattr("fastembed.TextEmbedding", FakeTextEmbedding)
    E5Embedder(cache_dir=tmp_path).embed_passages(["a passage"] * 216)  # a 3-hour video
    assert batch_sizes and max(batch_sizes) <= 16


def test_e5_concurrent_first_calls_load_the_model_once(tmp_path, monkeypatch):
    # The MCP server runs each tool call in its own thread.
    constructed, running, overlaps = [], [], []

    class SlowTextEmbedding:
        def __init__(self, model_name, **kwargs):
            time.sleep(0.2)  # reading ~2.2 GB of model files
            constructed.append(model_name)

        def embed(self, texts, **kwargs):
            running.append(1)
            overlaps.append(len(running))
            time.sleep(0.05)  # fastembed builds its ONNX session here, unguarded
            running.pop()
            return [np.ones(MODEL_DIM, np.float32) for _ in texts]

    monkeypatch.setattr("fastembed.TextEmbedding", SlowTextEmbedding)
    embedder = E5Embedder(cache_dir=tmp_path)
    threads = [threading.Thread(target=embedder.embed_queries, args=(["q"],)) for _ in range(3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(constructed) == 1
    assert max(overlaps) == 1


def test_e5_model_that_cannot_be_loaded_is_a_clean_error(tmp_path, monkeypatch):
    class Offline:
        def __init__(self, model_name, **kwargs):
            raise ValueError(f"Could not load model {model_name} from any source.")

    monkeypatch.setattr("fastembed.TextEmbedding", Offline)
    with pytest.raises(EmbeddingUnavailable) as exc:
        E5Embedder(cache_dir=tmp_path).embed_queries(["q"])
    message = str(exc.value)
    assert MODEL_NAME in message and "huggingface.co" in message and str(tmp_path) in message


# --- Real model (downloads ~2.2 GB on first use) -----------------------------------------

SENTENCES = [
    "Focus is a skill you can train, and it starts with how you manage your visual attention.",
    "Die Aufmerksamkeitsspanne lässt sich durch regelmäßige Konzentrationsübungen verlängern.",
    "A fókuszálóképesség edzhető, és a reggeli napfény segít beállítani a cirkadián ritmust.",
    "Kälteexposition erhöht den Dopaminspiegel deutlich und über mehrere Stunden hinweg.",
    "Az alváshiány rontja a munkamemóriát, a döntéshozatalt és az érzelmi szabályozást.",
]


@pytest.fixture(scope="module")
def e5():
    return E5Embedder()


@pytest.mark.model
def test_e5_vectors_are_normalized(e5):
    vectors = e5.embed_passages(SENTENCES[:2])
    queries = e5.embed_queries(["hogyan javíthatom a fókuszomat?"])
    assert vectors.shape == (2, MODEL_DIM) and queries.shape == (1, MODEL_DIM)
    np.testing.assert_allclose(np.linalg.norm(vectors, axis=1), 1.0, rtol=1e-5)


@pytest.mark.model
def test_e5_every_passage_fits_the_model_input(e5):
    from tokenizers import Tokenizer

    # An independent, untruncated count of what the model would see, special tokens included.
    e5.count_tokens("warm up")  # makes sure the model (and its tokenizer.json) is in the cache
    tokenizer_file = next(model_cache_dir().glob("models--*e5-large*/snapshots/*/tokenizer.json"))
    tokenizer = Tokenizer.from_file(str(tokenizer_file))
    tokenizer.no_truncation()
    tokenizer.no_padding()

    segments = [
        Segment(start=i * 4.0, end=(i + 1) * 4.0, text=SENTENCES[i % len(SENTENCES)])
        for i in range(600)
    ]
    giant = " ".join(SENTENCES * 60)  # one caption event far over the limit
    segments.insert(300, Segment(start=1200.0, end=1260.0, text=giant))
    passages = chunk(segments, e5.count_tokens)

    sizes = [len(tokenizer.encode(f"passage: {p.text}").ids) for p in passages]
    assert len(passages) > 10
    assert max(sizes) <= 512
