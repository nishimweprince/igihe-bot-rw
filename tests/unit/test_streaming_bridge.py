import asyncio

import pytest

from igihe_assistant.generation.streaming import stream_tokens


class Pieces:
    model_id = "pieces"

    def __init__(self, pieces, boom_after=None):
        self._pieces = pieces
        self._boom_after = boom_after
        self.yielded = 0

    def stream(self, system, messages, max_tokens):
        for i, p in enumerate(self._pieces):
            if self._boom_after is not None and i == self._boom_after:
                raise RuntimeError("model down")
            self.yielded += 1
            yield p


async def _collect(gen, cancel_after=None):
    out = []
    cancel = asyncio.Event()
    async for piece in stream_tokens(gen, "s", [], 10, cancel=cancel):
        out.append(piece)
        if cancel_after is not None and len(out) >= cancel_after:
            cancel.set()
    return out


def test_pieces_arrive_in_order():
    assert asyncio.run(_collect(Pieces(["a", "b", "c"]))) == ["a", "b", "c"]


def test_generator_exception_is_reraised():
    with pytest.raises(RuntimeError, match="model down"):
        asyncio.run(_collect(Pieces(["a", "b"], boom_after=1)))


def test_cancel_stops_the_worker():
    gen = Pieces([str(i) for i in range(1000)])
    out = asyncio.run(_collect(gen, cancel_after=3))
    assert len(out) == 3
    assert gen.yielded < 1000
