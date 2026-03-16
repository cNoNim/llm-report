# llm-report

Small CLI tool that aggregates usage statistics from local `Codex`, `Claude Code`, and `Gemini CLI` sessions.

It can:

- collect raw aggregated usage as JSON
- render Markdown reports
- combine multiple homes into one report
- estimate cost from pricing catalogs

## Providers

- `codex`
- `claude`
- `gemini`

## Config

The CLI looks for config files in this order:

1. `--config PATH`
2. `./llm-report.toml`
3. `./llm-report.default.toml`

`llm-report.toml` is intended for local machine-specific setup and is ignored by git.
`llm-report.default.toml` is the tracked repo default.

Example:

```toml
[homes]
codex = ["~/.codex"]
claude = ["~/.claude"]
gemini = ["~/.gemini"]

[pricing]
codex = "pricing.openai.json"
claude = "pricing.anthropic.json"
gemini = "pricing.gemini.json"
```

CLI flags like `--home`, `--codex-home`, `--claude-home`, and `--gemini-home` override config-based home discovery for that run.

## Pixi

`pixi` is the recommended way to run this project locally.

Official installation docs:

- `https://pixi.sh`

Quick install options from the official docs:

```bash
curl -fsSL https://pixi.sh/install.sh | sh
```

On macOS with Homebrew:

```bash
brew install pixi
```

After installation, restart your shell so `pixi` is available in `PATH`.

## Usage

With `pixi`:

```bash
pixi run report-all
pixi run report-codex
pixi run report-claude
pixi run report-gemini
pixi run test
```

Directly:

```bash
PYTHONPATH=src python -m llm_report report
PYTHONPATH=src python -m llm_report collect --provider codex
PYTHONPATH=src python -m llm_report report --home ~/.claude --provider claude
```

## Output

- `collect` prints JSON
- `report` prints Markdown

Combined reports include:

- per-home summary
- per-model summary
- monthly summary
- estimated cost when pricing is available

## Development

Requirements:

- Python 3.12+
- `pixi` recommended for running tasks and tests

Test suite:

```bash
pixi run test
```

## Acknowledgments

This project was developed with substantial AI assistance using OpenAI Codex and Claude Code.
