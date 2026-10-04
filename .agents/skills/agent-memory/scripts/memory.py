#!/usr/bin/env python3
"""
Hindsight Agent Memory CLI Helper for Senior Developer Arsenal.
Supports both embedded Hindsight execution and REST client connectivity.
"""

import argparse
import os
import sys

def get_client(base_url: str = None):
    try:
        from hindsight_client import Hindsight
        url = base_url or os.getenv("HINDSIGHT_BASE_URL", "http://localhost:8888")
        return Hindsight(base_url=url)
    except ImportError:
        try:
            from hindsight import EmbeddedHindsight
            data_dir = os.getenv("HINDSIGHT_DATA_DIR", "./.hindsight_data")
            return EmbeddedHindsight(data_dir=data_dir)
        except ImportError:
            print("[Error] Neither 'hindsight-client' nor 'hindsight-all' is installed.")
            print("Run: pip install hindsight-client  OR  pip install hindsight-all")
            sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Senior Developer Arsenal - Hindsight Memory Manager")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # retain
    p_retain = subparsers.add_parser("retain", help="Store an architectural fact or guideline")
    p_retain.add_argument("--bank", "-b", required=True, help="Memory bank ID (e.g. project name)")
    p_retain.add_argument("--content", "-c", required=True, help="Content to retain")
    p_retain.add_argument("--url", help="Hindsight server URL")

    # recall
    p_recall = subparsers.add_parser("recall", help="Retrieve memories using hybrid search")
    p_recall.add_argument("--bank", "-b", required=True, help="Memory bank ID")
    p_recall.add_argument("--query", "-q", required=True, help="Query string")
    p_recall.add_argument("--url", help="Hindsight server URL")

    # reflect
    p_reflect = subparsers.add_parser("reflect", help="Synthesize reasoned guidance from memory bank")
    p_reflect.add_argument("--bank", "-b", required=True, help="Memory bank ID")
    p_reflect.add_argument("--query", "-q", required=True, help="Query / Question")
    p_reflect.add_argument("--url", help="Hindsight server URL")

    args = parser.parse_args()
    client = get_client(args.url)

    if args.command == "retain":
        res = client.retain(bank_id=args.bank, content=args.content)
        print(f"[SUCCESS] Retained memory in bank '{args.bank}': {res}")
    elif args.command == "recall":
        results = client.recall(bank_id=args.bank, query=args.query)
        print(f"--- Recalled Memories ({args.bank}) ---")
        print(results)
    elif args.command == "reflect":
        reflection = client.reflect(bank_id=args.bank, query=args.query)
        print(f"--- Reflection ({args.bank}) ---")
        print(reflection)

if __name__ == "__main__":
    main()
