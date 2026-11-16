# Taking Stack House live at https://stackhouse.alsalemkuwait.com

The app runs on **Railway** (about $5/month), the code is kept in a **private GitHub repository**, and **GoDaddy** points `stackhouse.alsalemkuwait.com` at Railway. Railway provides the https certificate automatically.

Your existing setup on alsalemkuwait.com (Microsoft 365 email and the GoDaddy page) is **not touched**. We only *add* two DNS records.

Time needed: about 30 minutes, plus up to 30 minutes waiting for DNS.

> **Heads-up about your work network:** the firewall on the network this PC uses blocks alsalemkuwait.com. The live site will probably not open there. Do the testing on your phone using **mobile data or home Wi-Fi**. If you want it to work at the office too, ask IT to allow `stackhouse.alsalemkuwait.com`.

---

## Step 1 — GitHub: create an empty private repository (2 min)

1. Go to https://github.com/new
2. **Repository name:** `stack-house`
3. Choose **Private**.
4. Leave *Add a README*, *.gitignore* and *license* **unticked** (it must be empty).
5. Click **Create repository** and copy its address, e.g. `https://github.com/YOUR-NAME/stack-house.git`.
6. Paste that address to Claude. Claude commits the code and pushes it. The first time, a **GitHub sign-in window** pops up on this PC — sign in there.

## Step 2 — Railway: deploy the app (10 min)

1. Go to https://railway.com and choose **Login → Continue with GitHub**.
2. Pick the **Hobby** plan ($5/month, includes $5 of usage — this app needs far less). A trial also works for testing, but the site stops when the trial ends.
   - Recommended: *Workspace settings → Usage* → set a **usage limit** (e.g. $10) so there are never surprise charges.
3. **New Project → Deploy from GitHub repo**. If asked, *Configure GitHub App* and give Railway access to **only** the `stack-house` repository. Pick `stack-house`.
4. Railway starts building straight away (it finds the `Dockerfile` and `railway.json`). The first build takes 2–4 minutes.
5. **Add the storage volume — this is essential.** Without it, all orders, people and settings are wiped on every restart.
   - In the project canvas, **right-click the stack-house service → Attach volume** (or press `Ctrl+K` and type *volume*).
   - **Mount path:** `/data`
   - Railway redeploys the service with the volume attached.
6. **Get a test address:** click the service → **Settings → Networking → Public Networking → Generate Domain**. If it asks for a port, enter **8080**. You get an address like `https://stack-house-production-xxxx.up.railway.app`. Open it — you should see the *Welcome to Stack House* page. **Don't create the admin account yet** if you want it done from your phone in Kuwait time (see step 4).

Nothing else needs configuring. The `Dockerfile` already sets the following:
- https only
- secure login cookies
- data stored in `/data`
- the push-notification contact

## Step 3 — GoDaddy: point stackhouse.alsalemkuwait.com at Railway (5 min + waiting)

1. In Railway: service → **Settings → Networking → + Custom Domain** → type `stackhouse.alsalemkuwait.com` → port **8080**.
2. Railway now shows the DNS records to add — usually **two**:

   | Type  | Name (host)                 | Value                                         |
   |-------|-----------------------------|-----------------------------------------------|
   | CNAME | `stackhouse`                | something like `abc123.up.railway.app`        |
   | TXT   | `_railway-verify.stackhouse`| something like `railway-verify=…`             |

   Copy the values **exactly** from Railway (use its copy buttons).
3. In GoDaddy: sign in → **My Products** → next to **alsalemkuwait.com** click **DNS** (or *Manage DNS*).
4. Click **Add New Record**:
   - **Type:** CNAME · **Name:** `stackhouse` · **Value:** the Railway target · **TTL:** 1/2 hour (default is fine) → **Save**.
5. **Add New Record** again:
   - **Type:** TXT · **Name:** `_railway-verify.stackhouse` · **Value:** the Railway verification text → **Save**.

   GoDaddy adds `.alsalemkuwait.com` to the name by itself. Type only the part shown above.
6. **Do not change or delete any existing record.** The MX, TXT and `@` records are your email and current website.
7. Wait. Railway shows a green tick next to the domain when DNS is found and the certificate is issued. This usually takes 5–30 minutes, occasionally a few hours. Claude can check the public DNS for you in the meantime.

## Step 4 — First use (5 min)

On your **phone, on mobile data**:
1. Open **https://stackhouse.alsalemkuwait.com**.
2. Create your admin account.
   - The page shows *Kitchen timezone: Asia/Kuwait* (or Asia/Riyadh, which is the same time). If it shows something else, fix it later in **Admin → Settings**.
   - Keep *Start with a sample menu* ticked if you want example dishes to edit.
3. **Admin → People:** add everyone, and add the chef with role **Chef**.
4. **Admin → Families:** set each family's usual number of people.
5. **Admin → Settings:** check working hours, meal times, lock time and reminder times.
6. **Admin → Menu:** replace the sample dishes with the real ones and add photos.

## Step 5 — Testing on the live site (15 min)

Make two test accounts in **Admin → People**: `test-family` (a member of any family) and `test-chef` (role Chef). Use two phones — yours plus someone else's — or a phone plus a home computer.

| # | What to do | What should happen |
|---|------------|--------------------|
| 1 | Install the app on the phone. **Android/Chrome:** ⋮ menu → *Install app* / *Add to Home screen*. **iPhone/Safari:** Share → *Add to Home Screen*, then open it from the new icon. | Stack House opens full-screen with its own icon. |
| 2 | On each phone: **Me → Turn on notifications → Allow → Send a test**. | A “🔔 Test notification” pops up. |
| 3 | As `test-family`: **Plan → tomorrow → Yes lunch → pick dishes → Save plan**. | The chef's phone gets “🏠 … family is set for …”. |
| 4 | As `test-family`: **Order now → pick a dish → Send**. Lock the chef's phone first. | The chef's phone shows “🚨 Order now …” even while locked. |
| 5 | As `test-chef`: **Kitchen → Accept (20 min)**, then **Mark ready**. | The family's phone gets “👨‍🍳 The kitchen is on it”, then “✅ Your order is ready”. |
| 6 | **Reminder test** (do it before the lock time, 22:00, on a day when the kitchen is open tomorrow): make sure `test-family`'s family has *not* set tomorrow — use a family that hasn't planned. Then **Admin → Settings → Daily reminders → add a time 3 minutes from now → Save settings**. | Within about 1 minute of that time, the family's phone gets “🍽️ What is your family eating tomorrow?”. Afterwards, remove the test time. |
| 7 | **Data survives a restart:** Railway → service → **Deployments** → ⋮ on the latest one → **Redeploy**. Wait ~1 minute, then reopen the site. | You are still logged in, and orders and people are all still there. If everything is gone, the volume is not mounted at `/data` (step 2.5). |
| 8 | **Admin → Settings → Download backup**. | A `stackhouse-backup-….zip` file downloads. |
| 9 | Delete the two test accounts (**Admin → People → edit → Delete**). | |

**Automatic checks:** with the site live, Claude can run `tools/smoke_test.py` against the Railway test address. It checks:
- https and the certificate
- the redirect from http to https
- security headers
- the app files and notification setup
- logging in, if you give a username and password through environment variables

From a computer that isn't on the work network, you can also run it yourself:

```bash
.venv\Scripts\python tools\smoke_test.py https://stackhouse.alsalemkuwait.com
```

## Living with it

- **Updates:** Claude changes the code, commits and pushes. Railway rebuilds and restarts automatically in 1–2 minutes. Reminders keep their schedule.
- **Backups:** download one from **Admin → Settings** now and then (for example, monthly). To restore one, ask Claude: the zip holds the whole database and all photos.
- **Logs:** Railway → service → **Deployments → View logs**. Paste them to Claude if something looks wrong.
- **Keep one copy running.** Don't add replicas in Railway; the database and the reminder timer expect exactly one.

## If something goes wrong

| Problem | Fix |
|---------|-----|
| Build fails | Railway → Deployments → *View logs* → send the red lines to Claude. |
| “Application failed to respond” | Service → Settings → Networking: the domain's port must be **8080**. |
| Domain stuck on “waiting for DNS” | Check both GoDaddy records against Railway's values, character for character. Ask Claude to check the public DNS. |
| Site won't open at the office | The work firewall blocks the domain. Use mobile data, or ask IT to allow it. |
| Can't log in | Always use the **https://** address. Ask an admin to reset the password in Admin → People. |
| No notifications on iPhone | Needs iOS 16.4+, and Stack House must be opened from its **Home Screen icon**. Check iPhone *Settings → Notifications → Stack House*. |
| Data disappeared after a restart | The `/data` volume is missing — attach it (step 2.5). |
