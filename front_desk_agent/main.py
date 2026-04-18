"""
Zara — Zyana Systems Front Desk AI Agent
Entry point.
 yes
Usage:
    python3 main.py                        # voice mode, visitor (default)
    python3 main.py --text                 # text mode, visitor
    python3 main.py --mode outreach        # voice mode, sales outreach
    python3 main.py --mode owner           # voice mode, Naqiyah's assistant
    python3 main.py --mode owner --text    # text mode, owner (great for testing)
    python main.py --mode outreach --text # text mode, outreach (test sales script)

Modes:
    visitor  — greets walk-in visitors, logs arrivals, books meetings
    outreach — calls leads, qualifies prospects, books discovery calls
    owner    — Naqiyah's direct AI assistant (standup, pipeline, strategy)
"""

import argparse

import config
from assistant import FrontDeskAssistant


def main():
    parser = argparse.ArgumentParser(
        description=f"{config.AGENT_NAME} — {config.COMPANY_NAME} Front Desk AI"
    )
    parser.add_argument(
        "--text",
        action="store_true",
        help="Text mode: use keyboard + terminal instead of mic + speaker",
    )
    parser.add_argument(
        "--mode",
        choices=["visitor", "outreach", "owner"],
        default=config.DEFAULT_MODE,
        help="Agent mode: visitor | outreach | owner (default: visitor)",
    )
    args = parser.parse_args()

    assistant = FrontDeskAssistant(text_mode=args.text, mode=args.mode)
    assistant.run_loop()


if __name__ == "__main__":
    main()
