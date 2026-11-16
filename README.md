# Stack House Kitchen

A small web app for the four Stack House families (Mohammed, Salem, Ayman, Sabeeh) to order food from the shared cook and central kitchen.

## What it does

**Families**
- Everyone logs in with their own username and password.
- **Plan** lunch and dinner for today and the coming days (default: 7 days ahead). For each meal choose *Yes* or *No* (both meals are optional), pick any number of dishes from any category (Starters, Soups, Salads, Main dish, Desserts), and set **how many people** each dish is for. Add notes for the chef.
- Any member of a family can edit the family's plan until it **locks** (default 22:00 the day before).
- **Order now** sends an urgent request straight to the chef during working hours (anything outside the lunch/dinner plan). Families can follow its status: waiting → being prepared (with ready time) → ready → delivered.

**Chef (Kitchen screen)**
- Live list of *Order now* requests with Accept (with ready time), Ready, Delivered and Decline (with a reason) buttons, plus an optional sound alert.
- For any day: which family is set / said no / hasn't decided, a **prep list** with total servings per dish broken down by family, every family's notes, and a print view.

**Notifications** (in the app's bell, and as phone/desktop notifications when turned on)
- **Daily reminders** at configurable times (default 18:00 and 21:00) to families that haven't set tomorrow's food.
- The chef is told whenever a family **is set** for a day, changes its plan, or makes a late change.
- The chef gets an **urgent alert** for every *Order now* request.
- The chef gets a summary when orders lock (including who never set), and a morning brief when the kitchen opens.

**Admins**
- Add, edit, hide or delete dishes (with photos) and categories.
- Add people, put them in a family or make them the chef, reset passwords, grant admin access, give someone the chef's alerts.
- Families: name, colour, and usual number of people (the starting number when adding a dish).
- Settings: kitchen timezone, lunch/dinner times (or switch a meal off), **working hours for each day of the week**, lock time, reminder times, how far ahead families can plan, closed days/holidays, whether *Order now* is limited to working hours.

## Run it on this computer (Windows)

You need Python 3.10 or newer.

```bash
python -m venv .venv
```

```bash
.venv\Scripts\python -m pip install -r requirements.txt
```

```bash
.venv\Scripts\python run.py
```

Open http://localhost:8000. The first visit asks you to create the first **admin** account (and offers a sample menu you can edit). Then go to **Admin → People** to add the other family members and the chef.

To let phones on the same Wi-Fi use it, start it with `--host 0.0.0.0` and open `http://<this-computer's-IP>:8000` on the phone (Windows may ask to allow Python through the firewall):

```bash
.venv\Scripts\python run.py --host 0.0.0.0
```

All data (database, dish photos, keys) lives in the `data` folder. Back it up by copying that folder while the app is stopped.

## Phone notifications

Reminders and alerts always appear in the app (bell icon). To also get them as **phone notifications**, each person opens **Me → Turn on notifications** on their device. Two rules from the browsers themselves:

1. The site must be opened over **https** (or on `localhost`). A plain `http://192.168.x.x` address on Wi-Fi works for ordering but cannot send phone notifications.
2. On **iPhone/iPad** (iOS 16.4+), first open the site in Safari, tap **Share → Add to Home Screen**, open Stack House from the home screen, then turn on notifications. Android (Chrome) works directly in the browser.

For https you can either host it online, or keep it on a home computer and expose it with a tunnel such as Cloudflare Tunnel or Tailscale Funnel. Whatever you choose, the server must stay on all day for the reminders to go out on time.

**The live setup for Stack House (Railway + GitHub + stackhouse.alsalemkuwait.com) is described step by step in [DEPLOY.md](DEPLOY.md).** The `Dockerfile` and `railway.json` in this folder are what Railway uses.

### Settings for hosting

| Environment variable | Meaning |
| --- | --- |
| `PORT` / `STACKHOUSE_HOST` | Port and address to listen on (default `8000`, `127.0.0.1`) |
| `STACKHOUSE_DATA` | Folder for the database and photos (default `./data`; or `run.py --data`) |
| `STACKHOUSE_SECURE_COOKIES=1` | Set when the site is served over https |
| `STACKHOUSE_TRUST_PROXY=1` | Set when running behind a reverse proxy or tunnel |
| `STACKHOUSE_FORCE_HTTPS=1` | Redirect http:// to https:// and send HSTS (behind an https proxy) |
| `STACKHOUSE_VAPID_SUBJECT` | Contact for push services, e.g. `mailto:you@yourdomain.com` |

Run a single server process (the built-in `run.py` does this); reminders are sent by a background thread inside it.

## Tests

```bash
.venv\Scripts\python -m unittest discover -s tests -t .
```

## Project layout

```
run.py              start the server (Waitress)
app/__init__.py     app setup, security headers, static files
app/api.py          JSON API used by the web page
app/orders.py       meal plans, Order now requests, kitchen prep lists
app/rules.py        working hours, service days and lock times
app/scheduler.py    daily reminders, lock summary, morning brief
app/notify.py       in-app notifications and Web Push
app/settings.py     kitchen settings and validation
app/db.py           SQLite schema and first-run data
app/static/         the web app (HTML, CSS, JavaScript, icons, service worker)
tests/              automated tests
tools/smoke_test.py check a running site from the outside
Dockerfile          production image (Railway)
railway.json        Railway build/health-check settings
```
