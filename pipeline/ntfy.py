"""Push notifications through ntfy.

The topic acts as a password, so it's read from the environment (an Actions
secret) and never printed or written to disk.
"""

import os

DEFAULT_SERVER = "https://ntfy.sh"


def send(session, title: str, message: str, priority: str = "default",
         tags: str = "", topic: str | None = None, server: str | None = None) -> bool:
    """Send a notification. Returns False (and does nothing) if no topic is configured."""
    topic = topic or os.environ.get("NTFY_TOPIC", "").strip()
    if not topic:
        print("ntfy: NTFY_TOPIC not set; skipping notification")
        return False
    server = (server or os.environ.get("NTFY_SERVER") or DEFAULT_SERVER).rstrip("/")
    headers = {"Title": title.encode("ascii", "replace").decode(), "Priority": priority}
    if tags:
        headers["Tags"] = tags
    resp = session.post(f"{server}/{topic}", data=message.encode("utf-8"),
                        headers=headers, timeout=30)
    if resp.status_code >= 400:
        # Don't echo the URL: it contains the topic.
        print(f"ntfy: send failed with HTTP {resp.status_code}")
        return False
    return True


def main(argv=None) -> int:
    import argparse

    from .http import make_session

    ap = argparse.ArgumentParser(description="Send an ntfy notification (topic from NTFY_TOPIC)")
    ap.add_argument("--title", required=True)
    ap.add_argument("--message", required=True)
    ap.add_argument("--priority", default="default")
    ap.add_argument("--tags", default="")
    ap.add_argument("--strict", action="store_true",
                    help="exit 1 if the topic is missing or the send fails")
    args = ap.parse_args(argv)
    ok = send(make_session(), args.title, args.message, args.priority, args.tags)
    return 1 if args.strict and not ok else 0


if __name__ == "__main__":
    raise SystemExit(main())
