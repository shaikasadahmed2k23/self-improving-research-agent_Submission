"""Create or update the Hugging Face Space (Docker SDK) and push the app.

Usage:  python scripts/deploy_hf.py [--space NAME]
Needs HF_TOKEN in .env (write access). API keys are copied from .env into Space secrets; values are never printed.
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent import config  # noqa: E402,F401  (loads .env into the environment)

SECRETS = ["GROQ_API_KEY", "GOOGLE_API_KEY", "TAVILY_API_KEY", "NVIDIA_API_KEY"]
# Demo defaults on the Space (visible and editable in the Space settings)
VARIABLES = {
    "TOKEN_SAVER": "true",
    "GROQ_MODEL": "openai/gpt-oss-20b",
    "GROQ_MODEL_STRONG": "openai/gpt-oss-120b",
    "USE_STRONG_MODEL": "false",
    "LLM_FALLBACKS": "true",
}
EXCLUDE_PREFIXES = ("tests/", "reports/", "data/", "deploy/")
EXCLUDE_FILES = {"CLAUDE.md", "ASSIGNMENT.md", ".env.example", ".gitignore", "README.md"}


def app_files() -> list[str]:
    tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
    return [f for f in tracked if not f.startswith(EXCLUDE_PREFIXES) and f not in EXCLUDE_FILES and not f.endswith(".gitkeep")]


def main() -> int:
    from huggingface_hub import CommitOperationAdd, HfApi

    parser = argparse.ArgumentParser()
    parser.add_argument("--space", default="self-improving-research-agent")
    args = parser.parse_args()

    token = os.getenv("HF_TOKEN", "")
    if not token:
        print("HF_TOKEN is not set in .env; stopping.")
        return 1
    api = HfApi(token=token)
    repo_id = f"{api.whoami()['name']}/{args.space}"
    api.create_repo(repo_id, repo_type="space", space_sdk="docker", private=False, exist_ok=True)
    print(f"Space: {repo_id}")

    for key in SECRETS:
        if os.getenv(key):
            api.add_space_secret(repo_id, key, os.environ[key])
            print(f"  secret {key}: set")
        else:
            print(f"  secret {key}: missing in .env, skipped")
    for key, value in VARIABLES.items():
        api.add_space_variable(repo_id, key, value)
        print(f"  variable {key}={value}")

    files = app_files()
    ops = [CommitOperationAdd(path_in_repo=f, path_or_fileobj=str(ROOT / f)) for f in files]
    ops.append(CommitOperationAdd(path_in_repo="README.md", path_or_fileobj=str(ROOT / "deploy" / "space_README.md")))
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    api.create_commit(repo_id, repo_type="space", operations=ops, commit_message=f"Deploy from GitHub {head}")
    print(f"  uploaded {len(ops)} files (git {head})")
    print(f"URL: https://huggingface.co/spaces/{repo_id}")
    print(f"App: https://{repo_id.replace('/', '-').replace('_', '-').lower()}.hf.space")
    return 0


if __name__ == "__main__":
    sys.exit(main())
