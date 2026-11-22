"""Deploy Lattice Space to Hugging Face Spaces."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from huggingface_hub import HfApi


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Deploy interactive demo to Hugging Face Spaces"
    )
    parser.add_argument(
        "--token",
        default=os.getenv("HF_TOKEN"),
        help="Hugging Face user access token (or set HF_TOKEN env var)",
    )
    parser.add_argument(
        "--space-name",
        default="lattice-preemption-demo",
        help="Name for the Hugging Face Space repository",
    )
    parser.add_argument(
        "--sdk",
        default="static",
        choices=["static", "gradio", "docker"],
        help="Space SDK type (default: static)",
    )
    args = parser.parse_args()

    token = args.token
    if not token:
        print(
            "Error: No Hugging Face token provided. Pass --token or set HF_TOKEN.",
            file=sys.stderr,
        )
        sys.exit(1)

    api = HfApi(token=token)
    user_info = api.whoami()
    username = user_info["name"]
    repo_id = f"{username}/{args.space_name}"

    print(f"Authenticated as Hugging Face user: {username}")
    print(f"Creating Space: {repo_id} (SDK: {args.sdk})...")
    api.create_repo(
        repo_id=repo_id,
        repo_type="space",
        space_sdk=args.sdk,
        exist_ok=True,
    )

    space_dir = Path(__file__).resolve().parent.parent / "spaces" / "preemption-demo"
    print(f"Uploading files from {space_dir} to {repo_id}...")
    api.upload_folder(
        folder_path=str(space_dir),
        repo_id=repo_id,
        repo_type="space",
        ignore_patterns=["__pycache__/*", "*.pyc"],
    )

    space_url = f"https://huggingface.co/spaces/{repo_id}"
    print("\nSuccessfully deployed to Hugging Face Spaces!")
    print(f"Live Space URL: {space_url}")


if __name__ == "__main__":
    main()
