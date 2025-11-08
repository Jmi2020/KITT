import pytest

from brain.routing.summarizer import HermesSummarizer


class DummyClient:
    def __init__(self):
        self.last_prompt = None

    async def generate(self, prompt, model=None, tools=None):  # noqa: D401
        self.last_prompt = prompt
        return {"response": "condensed result"}


@pytest.mark.asyncio
async def test_hermes_summarizer_formats_agent_trace(monkeypatch):
    monkeypatch.setenv("HERMES_SUMMARY_ENABLED", "1")
    client = DummyClient()
    summarizer = HermesSummarizer(client=client)

    steps = [{"thought": "compare data", "observation": "GDP = 2.1%"}]
    summary = await summarizer.summarize("Very long answer" * 200, steps)

    assert summary == "condensed result"
    assert client.last_prompt is not None
    assert "Step 1" in client.last_prompt
    assert "final_answer" in client.last_prompt


def test_should_summarize_prefers_truncated(monkeypatch):
    monkeypatch.setenv("HERMES_SUMMARY_ENABLED", "1")
    summarizer = HermesSummarizer(client=DummyClient())

    assert summarizer.should_summarize(output_len=100, truncated=True, has_agent_steps=False)
    assert not summarizer.should_summarize(output_len=200, truncated=False, has_agent_steps=False)
