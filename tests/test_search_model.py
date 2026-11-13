import pytest

from video_to_rag.captions import Video
from video_to_rag.chunking import Passage
from video_to_rag.embedding import E5Embedder
from video_to_rag.library import Library
from video_to_rag.search import search

pytestmark = pytest.mark.model

PASSAGES = {
    "focus": "If you want to improve your focus at work, start by narrowing your visual "
    "attention: look at a single point for thirty to sixty seconds, then work in blocks of about "
    "ninety minutes and remove your phone from the room.",
    "caffeine": "Delay your caffeine intake by ninety to one hundred and twenty minutes after "
    "waking to avoid the afternoon crash, and stop drinking coffee eight hours before sleep.",
    "cold": "Deliberate cold exposure, such as an ice bath or a cold shower for one to three "
    "minutes, increases dopamine and norepinephrine for several hours afterwards.",
    "sleep": "To fall asleep more easily, view morning sunlight within the first hour after "
    "waking, keep your bedroom cool and dark, and avoid bright lights late at night.",
    "exercise": "Zone two cardio, a pace at which you can still hold a conversation, improves "
    "mitochondrial health; aim for about three hours of it every week.",
}


def test_hungarian_question_finds_english_passage(tmp_path):
    embedder = E5Embedder()
    library = Library.open_for_write(
        tmp_path / "library.sqlite3", embedder.model_name, embedder.dim
    )
    video = Video(
        "abc123DEF45", "Toolkit", "UC_A", "Huberman Lab", "2024-03-11", 7200, "en", "auto"
    )
    texts = list(PASSAGES.values())
    passages = [Passage(i, i * 60.0, i * 60.0 + 60, t) for i, t in enumerate(texts)]
    library.store(video, passages, embedder.embed_passages(texts))

    result = search(library, embedder, ["Hogyan tudom javítani a fókuszomat munka közben?"])

    first = result.hits[0]
    assert first.text == PASSAGES["focus"]  # the English original, verbatim
    assert first.language == "en"
