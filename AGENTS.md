## Project scope

- Build only the MVP defined in shockgraph-ai-project-spec.md.
- Do not implement live trading, order placement, or personalized buy/sell advice.
- Do not add Kafka, Kubernetes, or microservices.

## Financial correctness

- Store all market timestamps in UTC.
- Never use observations created after an event resolution in model features.
- The same event_id must never appear in more than one data split.
- Every model result must report sample size and uncertainty.
- Do not describe lagged association as causation.
- Keep raw API payloads immutable and record their hashes.
- LLM summaries may only use numbers present in validated JSON.

## Engineering workflow

- Treat each project-development request as two consecutive days from the 21-day plan,
  unless the user explicitly changes the scope.
- End every two-day delivery with `docs/reviews/day-XX-YY-review.md` containing the
  changed code structure, exact verification results, and a user inspection checklist.
- Write or update tests before fixing financial calculation bugs.
- Run `make quality` and `make test` before completing a task.
- Do not add a production dependency without documenting why it is needed.
- Keep collectors idempotent.
- Never commit API keys, tokens, account identifiers, or credentials.
- Use read-only public endpoints or demo environments.
