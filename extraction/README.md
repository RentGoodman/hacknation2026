# extraction

LLM extraction of rental housing rule records from the source corpus, with verbatim quote checks.

The current pipeline is `src/extraction/v3/`. See the [main README](../README.md#1-extraction-extraction) for how it fits into the project.

```sh
uv run --with pytest python -m pytest tests -q            # tests, model calls mocked
PYTHONPATH=src python -m extraction.v3.reproduce          # rebuild out/rules.json offline from cache/llm
PYTHONPATH=src python -m extraction.selfcheck             # submission self-check
```
