# Treasure or Trash

I have hundreds of old code projects sitting in a directory. Most of them are half-finished experiments and "I wonder if..." ideas I never came back to. This tool points an LLM at each one, gets a quick summary and a keep/bin verdict, then gives you a terminal UI to act on the results.

## How it works

There are two scripts:

`main.py` (the scanner) walks a directory looking for Python, Go, Laravel, and Node/Bun projects. It guesses whether they're simple or complex based on key file count, then sends a snapshot of each one to an LLM. You get back a one-line summary and a "treasure", "trash", or "unsure" verdict. Everything goes into a terse JSON file and a more easy to read markdown report.

`review.py` is a TUI that loads that JSON and lets you tag each project as keep, archive, or delete. Archiving zips the project before removing it. There's a dry-run mode so you can check the zips look right before anything gets deleted.

## Prerequisites

- Python 3.14+
- [uv](https://docs.astral.sh/uv/)
- An API key for any provider [litellm](https://docs.litellm.ai/) supports (Anthropic, OpenAI, etc.)

## Getting started

```bash
git clone git@github.com:ohnotnow/treasure-or-trash.git
cd treasure-or-trash
uv sync
```

Then create a `.env` file:

```
ANTHROPIC_API_KEY=sk-ant-...
# or whichever provider you want to use, eg, OPENAI_API_KEY, OPENROUTER_API_KEY...
```

## Usage

### Scanning

```bash
# Dry run first -- see what it finds without calling the LLM
uv run python main.py --dry-run /path/to/your/code

# Scan everything
uv run python main.py /path/to/your/code

# Filter by type or complexity
uv run python main.py -t python -c simple /path/to/your/code

# Do it in batches of 20
uv run python main.py -n 20 /path/to/your/code

# Pick up where you left off
uv run python main.py --resume projects.json /path/to/your/code

# Use a cheaper model
uv run python main.py -m anthropic/claude-haiku-4-5-20251001 /path/to/your/code
```

You get two output files:
- `projects.json` -- path, type, complexity, one-liner, and verdict for each project
- `report.md` -- longer descriptions and a summary table

### Reviewing

```bash
uv run python review.py projects.json

# Dry-run mode (no deletions, just creates zips)
uv run python review.py --dry-run projects.json

# Send archives somewhere specific
uv run python review.py --archive-dir ~/old-projects projects.json
```

Keyboard controls:

| Key | Action |
|-----|--------|
| `k` | Keep |
| `a` | Archive (zip then remove) |
| `d` | Delete |
| `f` | Cycle filter (all / keep / archive / delete) |
| `n` | Toggle dry-run |
| `Enter` | Apply actions (asks for confirmation) |
| `q` | Quit |

"Trash" verdicts default to delete, "treasure" to keep, "unsure" to keep. Safe by default.

## Tests

None yet. It's not like this is a MVP and could delete all your projects, right?  You trust me?  .... Right?

## Contributing

Fork it, `uv sync`, have at it.

## Licence

MIT. See [LICENSE](LICENSE).
