"""Terminal chat with the agent:  python scripts/chat_cli.py"""
import sys, warnings
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
warnings.filterwarnings("ignore")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from ifit.agent import Agent
from ifit.session import Session

def main():
    s = Session.create()
    a = Agent(s)
    print("IfIT agent (Qwen3.5-4B, demo money only). Type 'exit' to quit.\n")
    while True:
        try:
            q = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if q.lower() in ("exit", "quit"):
            break
        if not q:
            continue
        for ev in a.stream(q):
            if ev.kind == "tool_call":
                print(f"  [tool] {ev.name}({ev.data})")
            elif ev.kind == "text":
                print(ev.data, end="", flush=True)
            elif ev.kind == "error":
                print("ERROR:", ev.data)
        print("\n")

if __name__ == "__main__":
    main()
