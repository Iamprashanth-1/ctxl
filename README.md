# ctxl — Context Engineering CLI for AI Agents

**Reduce token waste. Prevent hallucination. Zero AI used.**

`ctxl` (pronounced "contextual") is a developer CLI tool that helps you manage the context window of AI coding agents (GitHub Copilot, Cursor, Claude, etc.) by generating compressed codebase skeletons, task-focused instructions, and session checkpoints — all using deterministic parsing, not AI.

## The Problem

AI coding agents (Copilot, Cursor, etc.) read your entire codebase to build context. A 3,000-line PySpark file burns ~750 tokens every time the agent references it. Over a session, your context window fills with noise, leading to:

- 🔴 **Hallucination** — the model starts making things up
- 🔴 **Token waste** — you pay for irrelevant context
- 🔴 **Lost focus** — the agent forgets your actual task

## The Solution

`ctxl` gives you three commands that prepare your environment *before* the AI agent reads it:

```bash
ctxl map          # Generate a compressed codebase skeleton (~95% token reduction)
ctxl init         # Generate task-focused Copilot instructions
ctxl checkpoint   # Save session state for safe /clear workflows
```

**Zero AI models. Zero API calls. Zero tokens burned by this tool.**

## Installation

```bash
pip install ctxl
```

## Quick Start

### `ctxl map` — Codebase Skeleton

Generate a compressed structural map of your codebase with line numbers:

```bash
ctxl map                      # Map current directory
ctxl map ./src                # Map a specific directory
ctxl map -e .py               # Only Python files
ctxl map -o codebase.md       # Save to file
ctxl map --clipboard          # Copy to clipboard for pasting into AI chat
```

**Before (raw file, ~750 tokens):**
```python
class DataPipeline:
    def __init__(self, spark, config):
        self.spark = spark
        self.config = config
        self.source_path = config.get("source_path", "/data/raw")
        # ... 60 more lines of implementation
    
    def clean_data(self, df, drop_nulls=True):
        string_cols = [f.name for f in df.schema.fields ...]
        # ... 20 more lines
```

**After (`ctxl map` output, ~50 tokens):**
```
L22: class DataPipeline:
    L25: def __init__(self, spark: SparkSession, config: Dict)
    L33: def load_data(self, table_name: str, filters: Optional[Dict] = None) -> DataFrame
    L42: def clean_data(self, df: DataFrame, drop_nulls: bool = True) -> DataFrame
    L52: def transform(self, df: DataFrame, rules: List[Dict]) -> DataFrame
    L66: def validate(self, df: DataFrame) -> bool
    L75: def save(self, df: DataFrame, partition_cols: List[str] = None) -> str
```

Line numbers (`L22:`, `L42:`) let the AI agent navigate directly to the right location.

### `ctxl init` — Copilot Instructions

Generate a `.github/copilot-instructions.md` file that GitHub Copilot reads natively:

```bash
ctxl init "Fix the data pipeline ETL bug"
ctxl init "Add authentication" -f auth.py -f models.py
ctxl init "Refactor tests" --no-map
```

### `ctxl checkpoint` — Session State

Save your progress before running `/clear` in Copilot Chat:

```bash
ctxl checkpoint save \
    -t "Fix ETL pipeline" \
    --done "Found the bug in clean_data()" \
    --state "Pipeline runs but output has wrong column order" \
    --next "Fix column ordering in transform()" \
    --file "data_pipeline.py"

ctxl checkpoint list          # List all checkpoints
ctxl checkpoint show          # Show latest checkpoint
```

## Supported Languages

`ctxl map` uses [Tree-sitter](https://tree-sitter.github.io/) for parsing and supports:

| Language | Extensions |
|----------|-----------|
| Python | `.py` |
| JavaScript | `.js`, `.jsx` |
| TypeScript | `.ts`, `.tsx` |
| Java | `.java` |

More languages can be added easily via Tree-sitter grammars.

## How It Works

```
Your Codebase (10,000+ tokens)
        │
        ▼
   Tree-sitter Parser (deterministic, local, free)
        │
        ▼
   AST → Extract signatures + line numbers
        │
        ▼
   Compressed Skeleton (~500 tokens)
        │
        ▼
   AI Agent reads skeleton instead of raw code
        │
        ▼
   90-95% fewer tokens burned 🎉
```

## License

MIT
