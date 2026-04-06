# Treasure or Trash

I have hundreds of old code projects sitting in a directory. Most of them are half-finished experiments, tutorial follow-alongs, and "I wonder if..." ideas I never came back to. This tool points an LLM at each one, gets a quick summary and a keep/bin verdict, then gives me a terminal UI to act on the results.

## How it works

There are two scripts:

`main.py` (the scanner) walks a directory looking for Python, Go, Laravel, and Node/Bun projects. It finds them by their marker files (`go.mod`, `artisan`, `package.json`, `pyproject.toml`, etc.), guesses whether they're simple or complex based on file count, then sends a snapshot of each one to an LLM. You get back a one-line summary and a "treasure", "trash", or "unsure" verdict. Everything goes into a JSON file and a markdown report.

`review.py` (the reviewer) is a Textual TUI that loads that JSON and lets you tag each project as keep, archive, or delete. Archiving zips the project before removing it. There's a dry-run mode so you can check the zips look right before anything gets deleted.

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

```bash
cp .env.example .env  # or just create one
```

```
ANTHROPIC_API_KEY=sk-ant-...
```

Using a different provider? Set the right key instead (e.g. `OPENAI_API_KEY`). Litellm sorts out the routing.

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

None yet. The irony of a project about cleaning up half-finished projects being itself half-finished is not lost on me.

## Contributing

Fork it, `uv sync`, have at it. PRs welcome.

## Licence

MIT. See [LICENSE](LICENSE).
