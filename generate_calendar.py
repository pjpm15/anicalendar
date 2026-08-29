#!/usr/bin/env python3
"""
Generates subscribable .ics calendar files from AniList user lists.

For every account listed in config.json, this script:
  1. Queries the AniList GraphQL API for that user's anime list
     (filtered to the requested statuses, e.g. CURRENT / PLANNING).
  2. Pulls each show's upcoming airing schedule.
  3. Writes a standards-compliant .ics file to docs/<username>.ics

Run manually with:  python generate_calendar.py
The GitHub Action in .github/workflows/update.yml runs this on a schedule.
"""

import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

ANILIST_API = "https://graphql.anilist.co"
CONFIG_PATH = Path(__file__).parent / "config.json"
OUTPUT_DIR = Path(__file__).parent / "docs"

QUERY = """
query ($userName: String, $statusIn: [MediaListStatus]) {
  MediaListCollection(userName: $userName, type: ANIME, status_in: $statusIn) {
    lists {
      status
      entries {
        media {
          id
          siteUrl
          episodes
          title {
            romaji
            english
          }
          nextAiringEpisode {
            airingAt
            episode
          }
          airingSchedule(notYetAired: true, perPage: 25) {
            nodes {
              airingAt
              episode
            }
          }
        }
      }
    }
  }
}
"""

DEFAULT_STATUSES = ["CURRENT", "PLANNING"]


def hashed_filename(username: str, salt: str) -> str:
    """
    Turn an AniList username into a non-reversible, obscure filename so the
    published calendar URL doesn't reveal the username in plain text.
    `salt` should be a private value (e.g. a GitHub secret) so the hash
    can't be brute-forced from a known username list.
    """
    digest = hashlib.sha256(f"{salt}:{username.lower()}".encode()).hexdigest()
    return digest[:16]


def fetch_list(username: str, statuses: list[str]) -> dict:
    resp = requests.post(
        ANILIST_API,
        json={"query": QUERY, "variables": {"userName": username, "statusIn": statuses}},
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        timeout=30,
    )
    if resp.status_code == 404:
        raise ValueError(f"AniList user '{username}' not found.")
    resp.raise_for_status()
    payload = resp.json()
    if "errors" in payload and payload["errors"]:
        raise ValueError(f"AniList API error for '{username}': {payload['errors']}")
    return payload["data"]["MediaListCollection"]


def best_title(title_obj: dict) -> str:
    return title_obj.get("english") or title_obj.get("romaji") or "Unknown Title"


def unix_to_ics(ts: int) -> str:
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    return dt.strftime("%Y%m%dT%H%M%SZ")


def escape_ics_text(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def build_ics(username: str, collection: dict) -> str:
    now_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//anilist-calendar//github-actions//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:AniList Schedule - {escape_ics_text(username)}",
        "X-WR-TIMEZONE:UTC",
        # Ask calendar apps to refresh reasonably often (not all clients honor this).
        "X-PUBLISHED-TTL:PT6H",
        "REFRESH-INTERVAL;VALUE=DURATION:PT6H",
    ]

    seen_events = set()
    event_count = 0

    for lst in collection.get("lists", []):
        for entry in lst.get("entries", []):
            media = entry["media"]
            title = best_title(media["title"])
            site_url = media.get("siteUrl", "")
            media_id = media["id"]

            # Collect upcoming episodes: prefer the full airingSchedule list,
            # fall back to nextAiringEpisode if that's all we have.
            episodes = list(media.get("airingSchedule", {}).get("nodes", []) or [])
            if not episodes and media.get("nextAiringEpisode"):
                episodes = [media["nextAiringEpisode"]]

            for ep in episodes:
                airing_at = ep.get("airingAt")
                ep_num = ep.get("episode")
                if airing_at is None or ep_num is None:
                    continue

                uid = f"anilist-{media_id}-ep{ep_num}@anilist-calendar"
                if uid in seen_events:
                    continue
                seen_events.add(uid)

                dtstart = unix_to_ics(airing_at)
                summary = escape_ics_text(f"{title} - Episode {ep_num}")
                description = escape_ics_text(f"{title}, episode {ep_num}\n{site_url}")

                lines += [
                    "BEGIN:VEVENT",
                    f"UID:{uid}",
                    f"DTSTAMP:{now_stamp}",
                    f"DTSTART:{dtstart}",
                    "DURATION:PT30M",
                    f"SUMMARY:{summary}",
                    f"DESCRIPTION:{description}",
                ]
                if site_url:
                    lines.append(f"URL:{site_url}")
                lines.append("END:VEVENT")
                event_count += 1

    lines.append("END:VCALENDAR")
    print(f"  -> {event_count} upcoming episode(s) for {username}")
    return "\r\n".join(lines) + "\r\n"


def build_index_html(accounts: list[dict], salt: str) -> str:
    rows = []
    for acc in accounts:
        slug = hashed_filename(acc["username"], salt)
        rows.append(
            f'<li><a href="{slug}.ics">{slug}.ics</a></li>'
        )
    body = "\n      ".join(rows) if rows else "<li>No accounts configured.</li>"
    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>AniList Calendars</title></head>
<body>
  <h1>AniList Airing Calendars</h1>
  <p>Subscribe to a calendar below in Google Calendar / Apple Calendar / Outlook
     using its URL (use <code>webcal://</code> instead of <code>https://</code> for one-click
     subscribe on Apple devices).</p>
  <ul>
      {body}
  </ul>
  <p><em>Last generated: {datetime.now(timezone.utc).isoformat()}</em></p>
</body>
</html>
"""


def main() -> int:
    if not CONFIG_PATH.exists():
        print(f"Missing config file: {CONFIG_PATH}", file=sys.stderr)
        return 1

    salt = os.environ.get("FILENAME_SALT")
    if not salt:
        print(
            "Warning: FILENAME_SALT is not set. Filenames will still be "
            "hashed but with a fixed default salt, which is less secret. "
            "Set the FILENAME_SALT GitHub Actions secret for real use.",
            file=sys.stderr,
        )
        salt = "default-insecure-salt-please-set-a-real-one"

    config = json.loads(CONFIG_PATH.read_text())
    accounts = config.get("accounts", [])
    if not accounts:
        print("No accounts configured in config.json", file=sys.stderr)
        return 1

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    had_error = False
    for acc in accounts:
        username = acc.get("username", "").strip()
        statuses = acc.get("statuses") or DEFAULT_STATUSES

        if not username or username == "YOUR_ANILIST_USERNAME":
            print("Skipping placeholder account in config.json - edit config.json first.")
            continue

        print(f"Fetching list for {username} (statuses: {statuses})...")
        try:
            collection = fetch_list(username, statuses)
        except Exception as exc:  # noqa: BLE001
            print(f"  ! Failed to fetch {username}: {exc}", file=sys.stderr)
            had_error = True
            continue

        ics_text = build_ics(username, collection)
        out_path = OUTPUT_DIR / f"{hashed_filename(username, salt)}.ics"
        out_path.write_text(ics_text, encoding="utf-8")
        print(f"  -> wrote {out_path.name} (for {username})")

        # Be polite to AniList's rate limits between accounts.
        time.sleep(1)

    (OUTPUT_DIR / "index.html").write_text(build_index_html(accounts, salt), encoding="utf-8")

    return 1 if had_error else 0


if __name__ == "__main__":
    raise SystemExit(main())
