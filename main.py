"""
Treasure or Trash — scan a directory of projects and figure out what they actually do.

Detects project type (Python, Go, Laravel, Node/Bun), classifies complexity,
then uses an LLM to generate a one-line summary and fuller description.
Outputs a JSON index and a markdown report.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from litellm import completion

load_dotenv()

# Marker files that identify a project type
PROJECT_MARKERS = {
    "python": ["pyproject.toml", "setup.py", "setup.cfg", "requirements.txt", "Pipfile"],
    "golang": ["go.mod"],
    "laravel": ["artisan"],
    "node": ["package.json"],
}

# Directories to skip when scanning
SKIP_DIRS = {
    "node_modules", "vendor", ".venv", "venv", "__pycache__", ".git",
    ".idea", ".vscode", "dist", "build", ".next", ".nuxt", "storage",
    "bootstrap/cache", ".terraform", "target",
}

# Extensions worth reading for context
CODE_EXTENSIONS = {
    ".py", ".go", ".php", ".js", ".ts", ".tsx", ".jsx", ".vue", ".svelte",
    ".blade.php", ".css", ".html", ".sql", ".sh", ".yaml", ".yml", ".toml",
    ".json", ".md", ".env.example",
}

# Max characters to send to the LLM per project
MAX_CONTEXT_CHARS = 12_000


def detect_project_type(path: Path) -> str | None:
    """Return the project type based on marker files, or None if not a project."""
    for project_type, markers in PROJECT_MARKERS.items():
        for marker in markers:
            if (path / marker).exists():
                return project_type
    return None


def gather_source_files(path: Path) -> list[Path]:
    """Collect source files, skipping junk directories."""
    files = []
    for item in sorted(path.rglob("*")):
        if any(skip in item.parts for skip in SKIP_DIRS):
            continue
        if item.is_file() and item.suffix in CODE_EXTENSIONS:
            files.append(item)
    return files


def classify_complexity(project_type: str, source_files: list[Path], project_path: Path) -> str:
    """Classify a project as 'simple' or 'complex' based on file count and structure."""
    count = len(source_files)

    if project_type == "laravel":
        # Laravel is almost always complex, but check for default scaffolding
        custom_files = [
            f for f in source_files
            if "app/" in str(f.relative_to(project_path))
            or "routes/" in str(f.relative_to(project_path))
            or "database/migrations" in str(f.relative_to(project_path))
        ]
        return "simple" if len(custom_files) <= 3 else "complex"

    if project_type == "python":
        py_files = [f for f in source_files if f.suffix == ".py"]
        return "simple" if len(py_files) <= 3 else "complex"

    if project_type == "golang":
        go_files = [f for f in source_files if f.suffix == ".go"]
        return "simple" if len(go_files) <= 3 else "complex"

    if project_type == "node":
        code_files = [f for f in source_files if f.suffix in {".js", ".ts", ".tsx", ".jsx", ".vue", ".svelte"}]
        return "simple" if len(code_files) <= 3 else "complex"

    return "simple" if count <= 5 else "complex"


def build_project_snapshot(project_path: Path, source_files: list[Path]) -> str:
    """Build a text snapshot of the project for the LLM to read."""
    parts = []

    # Directory tree (just filenames, not contents)
    tree_lines = []
    for f in source_files[:80]:  # cap at 80 files for the tree
        tree_lines.append(str(f.relative_to(project_path)))
    parts.append("## File tree\n" + "\n".join(tree_lines))

    # Key config files first
    config_names = {
        "pyproject.toml", "package.json", "go.mod", "composer.json",
        "Cargo.toml", "README.md", "readme.md",
    }
    config_files = [f for f in source_files if f.name.lower() in {c.lower() for c in config_names}]
    other_files = [f for f in source_files if f not in config_files]

    chars_used = len(parts[0])
    budget = MAX_CONTEXT_CHARS - chars_used

    # Read config files first (they're the most informative)
    for f in config_files + other_files:
        if budget <= 0:
            break
        try:
            content = f.read_text(errors="replace")[:3000]
        except Exception:
            continue
        relative = str(f.relative_to(project_path))
        chunk = f"\n## {relative}\n```\n{content}\n```\n"
        if len(chunk) > budget:
            # Include a truncated version if we have some budget left
            if budget > 200:
                chunk = chunk[:budget]
            else:
                break
        parts.append(chunk)
        budget -= len(chunk)

    return "\n".join(parts)


def describe_project(snapshot: str, project_type: str, complexity: str, model: str) -> dict:
    """Ask the LLM to describe what this project does."""
    prompt = f"""You are analysing a {complexity} {project_type} project. Based on the source files below,
provide a description of what this project does or was trying to do.

Respond with ONLY valid JSON (no markdown fences) in this exact format:
{{
  "one_liner": "A single sentence summary, max 120 characters",
  "description": "A paragraph (3-5 sentences) describing the project's purpose, what it does, key technologies used, and current state (working, abandoned, prototype, etc).",
  "verdict": "treasure|trash|unsure"
}}

The verdict should be:
- "treasure" if this looks like a useful, working, or important project
- "trash" if this looks like an abandoned experiment, tutorial follow-along, or default scaffolding with no real content
- "unsure" if you genuinely can't tell

Be honest and direct. British humour welcome.

{snapshot}"""

    response = completion(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=500,
    )

    text = response.choices[0].message.content.strip()
    # Strip markdown fences if the model wraps them anyway
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    return json.loads(text)


def scan_directory(root: Path) -> list[dict]:
    """Scan a directory for projects and return their metadata."""
    projects = []
    root = root.resolve()

    for item in sorted(root.iterdir()):
        if not item.is_dir() or item.name.startswith("."):
            continue

        project_type = detect_project_type(item)
        if project_type is None:
            continue

        source_files = gather_source_files(item)
        complexity = classify_complexity(project_type, source_files, item)

        projects.append({
            "path": str(item),
            "name": item.name,
            "type": project_type,
            "complexity": complexity,
            "source_file_count": len(source_files),
            "source_files": source_files,
        })

    return projects


def generate_reports(projects: list[dict], output_dir: Path, model: str, dry_run: bool = False):
    """Generate the JSON index and markdown report."""
    json_entries = []
    md_lines = [
        "# Treasure or Trash — Project Report",
        f"\nGenerated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"\nScanned {len(projects)} projects.\n",
    ]

    # Group by verdict for the summary
    verdicts = {"treasure": [], "trash": [], "unsure": []}

    for i, project in enumerate(projects, 1):
        name = project["name"]
        print(f"  [{i}/{len(projects)}] {name} ({project['type']}, {project['complexity']})...", end=" ", flush=True)

        if dry_run:
            result = {
                "one_liner": f"[DRY RUN] {project['type']} project with {project['source_file_count']} source files",
                "description": "Dry run — no LLM call made.",
                "verdict": "unsure",
            }
        else:
            snapshot = build_project_snapshot(Path(project["path"]), project["source_files"])
            try:
                result = describe_project(snapshot, project["type"], project["complexity"], model)
            except Exception as e:
                print(f"ERROR: {e}")
                result = {
                    "one_liner": f"Error analysing project: {e}",
                    "description": f"Failed to analyse: {e}",
                    "verdict": "unsure",
                }

        verdict = result.get("verdict", "unsure")
        emoji = {"treasure": "💎", "trash": "🗑️", "unsure": "🤷"}.get(verdict, "🤷")
        print(f"{emoji} {result['one_liner']}")

        json_entries.append({
            "path": project["path"],
            "name": name,
            "type": project["type"],
            "complexity": project["complexity"],
            "source_file_count": project["source_file_count"],
            "one_liner": result["one_liner"],
            "verdict": verdict,
        })

        verdicts[verdict].append(name)

        md_lines.append(f"## {emoji} {name}")
        md_lines.append(f"\n**Type:** {project['type']} | **Complexity:** {project['complexity']} "
                        f"| **Files:** {project['source_file_count']} | **Verdict:** {verdict}")
        md_lines.append(f"\n> {result['one_liner']}")
        md_lines.append(f"\n{result['description']}\n")
        md_lines.append(f"📂 `{project['path']}`\n")
        md_lines.append("---\n")

    # Summary at the top
    summary_lines = [
        "\n## Summary\n",
        f"| Category | Count |",
        f"|----------|-------|",
        f"| 💎 Treasure | {len(verdicts['treasure'])} |",
        f"| 🗑️  Trash | {len(verdicts['trash'])} |",
        f"| 🤷 Unsure | {len(verdicts['unsure'])} |",
        "",
    ]
    # Insert summary after the header
    md_lines[3:3] = summary_lines

    # Write outputs
    json_path = output_dir / "projects.json"
    md_path = output_dir / "report.md"

    json_path.write_text(json.dumps(json_entries, indent=2) + "\n")
    md_path.write_text("\n".join(md_lines) + "\n")

    print(f"\n  JSON index: {json_path}")
    print(f"  Markdown report: {md_path}")

    return json_entries


def main():
    parser = argparse.ArgumentParser(
        description="Treasure or Trash — scan your projects and find out what they actually do."
    )
    parser.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="Directory to scan for projects (default: current directory)",
    )
    parser.add_argument(
        "-o", "--output",
        default=".",
        help="Output directory for reports (default: current directory)",
    )
    parser.add_argument(
        "-m", "--model",
        default="anthropic/claude-sonnet-4-20250514",
        help="LLM model to use via litellm (default: anthropic/claude-sonnet-4-20250514)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scan and classify projects without calling the LLM",
    )
    parser.add_argument(
        "--json-only",
        action="store_true",
        help="Only output JSON, skip markdown report",
    )
    parser.add_argument(
        "-t", "--type",
        choices=["python", "golang", "laravel", "node"],
        help="Only scan projects of this type",
    )
    parser.add_argument(
        "-c", "--complexity",
        choices=["simple", "complex"],
        help="Only scan projects of this complexity",
    )
    parser.add_argument(
        "-n", "--limit",
        type=int,
        default=0,
        help="Limit to first N projects (0 = all, useful for testing)",
    )
    parser.add_argument(
        "--resume",
        help="Path to existing projects.json — skip projects already analysed",
    )

    args = parser.parse_args()

    scan_root = Path(args.directory).resolve()
    output_dir = Path(args.output).resolve()

    if not scan_root.is_dir():
        print(f"Error: {scan_root} is not a directory", file=sys.stderr)
        sys.exit(1)

    print(f"Scanning {scan_root} for projects...\n")
    projects = scan_directory(scan_root)

    if not projects:
        print("No projects found.")
        sys.exit(0)

    # Apply filters
    if args.type:
        projects = [p for p in projects if p["type"] == args.type]
    if args.complexity:
        projects = [p for p in projects if p["complexity"] == args.complexity]

    # Resume support — skip already-analysed projects
    already_done = set()
    if args.resume:
        resume_path = Path(args.resume)
        if resume_path.exists():
            existing = json.loads(resume_path.read_text())
            already_done = {e["path"] for e in existing}
            projects = [p for p in projects if p["path"] not in already_done]
            print(f"Resuming — skipping {len(already_done)} already analysed projects.\n")

    if args.limit > 0:
        projects = projects[:args.limit]

    if not projects:
        print("No projects to analyse after filtering.")
        sys.exit(0)

    print(f"Analysing {len(projects)} projects...\n")
    entries = generate_reports(projects, output_dir, args.model, dry_run=args.dry_run)

    # If resuming, merge with existing results
    if already_done and args.resume:
        existing = json.loads(Path(args.resume).read_text())
        merged = existing + entries
        merged.sort(key=lambda e: e["name"].lower())
        json_path = output_dir / "projects.json"
        json_path.write_text(json.dumps(merged, indent=2) + "\n")
        print(f"\n  Merged {len(entries)} new + {len(existing)} existing = {len(merged)} total in {json_path}")


if __name__ == "__main__":
    main()
