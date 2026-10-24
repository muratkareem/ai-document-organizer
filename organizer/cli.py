"""Command-line entry point."""
import argparse


def main() -> int:
    parser = argparse.ArgumentParser(description="Organize local documents using Ollama.")
    parser.add_argument("directory", help="Directory containing documents")
    parser.parse_args()
    return 0
