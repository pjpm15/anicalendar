# AniList Airing Calendar

Generates subscribable `.ics` calendar feeds from one or more AniList
accounts' watch lists, auto-refreshed every 6 hours via GitHub Actions and
served free via GitHub Pages — **without your AniList username(s) or list
ever being committed to the repo.**

## How the privacy part works

- Your real account list lives only in a GitHub Actions **secret**
  (`ANILIST_ACCOUNTS_JSON`), never in a file in the repo.
- `config.json` is git-ignored — if you ever create one locally for testing,
  it won't get committed.
- Each account's `.ics` filename is a hash (e.g. `de9bea6f562dbffb.ics`),
  derived from the username plus a second secret (`FILENAME_SALT`) that only
  you know — so the published filename doesn't reveal your username, and
  it can't be brute-forced from a known username unless someone also knows
  your salt.

**Important caveat:** the repo can be public here (required for GitHub
Pages on the free tier), and the *generated calendar files themselves* are
still openly reachable by anyone who has the exact hashed URL — GitHub
Pages doesn't support authenticated/private sites below the Enterprise
Cloud plan. This setup hides your username and list from anyone browsing
the repo or guessing filenames; it does not add a login wall on the
calendar link itself. Don't share the `.ics` URL publicly if you'd rather
people not view your schedule.

## 1. Create the repo

Create a new **public** repository on GitHub (e.g. `anilist-calendar`) and
upload all files in this folder — **except** `config.example.json` is fine
to include as-is, it's just a template with a placeholder username.

## 2. Add two repo secrets

Go to **Settings → Secrets and variables → Actions → New repository
secret** and add:

1. **`ANILIST_ACCOUNTS_JSON`** — the real contents of your config, e.g.:

   ```json
   {"accounts": [
     {"username": "YourUsername1", "statuses": ["CURRENT", "PLANNING"]},
     {"username": "YourUsername2", "statuses": ["CURRENT"]}
   ]}
   ```

   (Same format as `config.example.json`, just with real usernames.)

2. **`FILENAME_SALT`** — any random string only you know, e.g. generate one
   with `openssl rand -hex 16` or just mash your keyboard. This determines
   your hashed filenames — write it down, since changing it later will
   change all your calendar URLs.

`statuses` is optional per account and defaults to `["CURRENT",
"PLANNING"]`. Valid values: `CURRENT`, `PLANNING`, `COMPLETED`, `DROPPED`,
`PAUSED`, `REPEATING`.

## 3. Enable GitHub Pages

**Settings → Pages → Build and deployment → Source** → **Deploy from a
branch** → branch `main`, folder `/docs`. Save.

Your site will be at:

```
https://YOUR-GH-USERNAME.github.io/anilist-calendar/
```

## 4. Run it

**Actions** tab → "Update AniList calendars" → **Run workflow** to trigger
the first run manually (otherwise it waits for the next scheduled run, up
to 6 hours).

After it finishes, check `docs/index.html` on your Pages site for the
hashed `.ics` links — one per account, in the order you listed them in the
secret.

## 5. Subscribe

- **Google Calendar**: Other calendars → `+` → "From URL" → paste the
  `https://...ics` link.
- **Apple Calendar / iOS**: use `webcal://...ics` instead of `https://...ics`
  for one-tap subscribe, or File → New Calendar Subscription.
- **Outlook**: Add calendar → Subscribe from web → paste the URL.

Calendar apps poll subscribed URLs on their own schedule (often every few
hours to once a day, and this varies by client — you can't force it), while
the GitHub Action keeps the underlying file itself updated every 6 hours.

## Notes / limitations

- Only *upcoming, not-yet-aired* episodes are included.
- Shows with no confirmed air date yet will simply have no events until
  AniList has schedule data for them — they'll appear automatically once
  available.
- Repo must stay **public** for GitHub Pages' free tier. If you want the
  *source repo* itself private too (not just usernames hidden), that
  requires GitHub Pro ($4/mo) — note the published calendar link is still
  publicly reachable either way, since Pages doesn't gate site access below
  Enterprise Cloud.
- Want a different refresh cadence? Edit the `cron` line in
  `.github/workflows/update.yml`.
- Changing `FILENAME_SALT` later changes every calendar's URL, so you'd
  need to re-subscribe in your calendar app.
