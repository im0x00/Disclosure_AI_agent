# Disclosure AI Agent

## Local setup

Install the locked Python environment:

```shell
uv sync --group dev
```

Copy `.env.example` to `.env`, then start the shared PostgreSQL service:

```shell
docker compose up -d postgres
```

Stop the service without deleting its data:

```shell
docker compose down
```

## Boundaries

- `corpus/`: source disclosure documents and metadata
- `semantics/`: human-reviewed YAML semantics
- `src/disclosure_ai/data/`: corpus loading and normalization
- `src/disclosure_ai/reasoning/`: LangGraph state and workflows
- `tests/`: test cases; its inner layout is intentionally undecided
