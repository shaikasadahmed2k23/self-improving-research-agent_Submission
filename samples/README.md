# Samples

## Reports (`outputs/`)
| File | What it shows |
|---|---|
| [01-before-memory-pinecone-10gb.md](outputs/01-before-memory-pinecone-10gb.md) | First run with an empty memory: the critic rejects the draft (3/10, third-party figures, "$3.33"), fix-up steps fetch the official page, the final report is accepted (9/10), and 2 lessons are learned |
| [02-after-memory-pinecone-25gb.md](outputs/02-after-memory-pinecone-25gb.md) | Fourth run, same setup: recalled lessons shape the plan, the first draft is accepted (9/10, 0 revisions) with 52% fewer tokens |
| [03-official-page-120b-pinecone-10gb.md](outputs/03-official-page-120b-pinecone-10gb.md) | All roles on gpt-oss-120b without memory: official page + calculator, accepted at revision 0 |

Each file starts with the run's metadata (models, critic scores, tools, tokens) and then the report exactly as the
agent wrote it.

## Traces (`traces/`)
Recorded runs (one JSON event per line). Open the app, set **Mode → Replay a recorded run**, pick one and press
**Replay**. No LLM calls are made.

| Trace | Run |
|---|---|
| `m4-qwen-run1-before-10gb` | Run #1: empty memory, 3/10 → 9/10, 1 revision, 28,411 tokens |
| `m4-qwen-run2-25gb` | Run #2: 2 lessons recalled, 6/10 → 9/10, 1 revision, 18,223 tokens |
| `m4-qwen-run3-40gb` | Run #3: 3 lessons recalled, 4/10 → 8/10 (revision limit), 38,509 tokens |
| `m4-qwen-run4-after-25gb` | Run #4: 4 lessons recalled, **9/10 at the first critique, 0 revisions, 13,604 tokens** |
| `m4-20b-before-10gb` | gpt-oss-20b "before" run (converted from a CLI log, so it has no report text) |

## Memory seed
`seed_memory.db` is the memory after the four qwen runs (4 runs, 5 lessons, 1 trusted source). The deployed app copies
it into place on a fresh start, so the **Memory** tab is not empty.
