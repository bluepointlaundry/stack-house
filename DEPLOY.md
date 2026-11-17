# Taking Stack House live at https://stackhouse.alsalemkuwait.com

| Piece | Service | Cost |
|-------|---------|------|
| Code | GitHub, private repository `bluepointlaundry/stack-house` | free |
| Website | **Vercel** (Hobby plan), region Singapore (`sin1`), next to the database | free |
| Database, photos, reminder timer | **Supabase**, project in the free **Stack House** organisation, region Singapore (ap-southeast-1) | free |
| Address | GoDaddy DNS: one CNAME record `stackhouse` pointing to Vercel | already paid |

Your existing alsalemkuwait.com email (Microsoft 365) and GoDaddy page are not touched.

> The firewall on the work network this PC uses blocks alsalemkuwait.com. Test from your phone on **mobile data or home Wi-Fi**.

## How the pieces work together

- **Vercel** runs the app (`index.py`) and serves the page files in `public/`.
- The app keeps everything in **Supabase Postgres**: people, menu, orders, settings and dish photos. It creates its tables on first start, with row-level security on, so Supabase's public API can't read them.
- **Reminders:** every minute, Supabase's `pg_cron` calls `https://…/api/cron/tick`. The call is protected by a secret stored only in the database. The app then sends any reminders, lock summaries and morning briefs that are due. **Admin → Settings** shows whether this timer is running.
- **Vercel settings (Project → Settings → Environment Variables):**
  - `DATABASE_URL`: the Supabase *Transaction pooler* address, still containing `[YOUR-PASSWORD]`
  - `DATABASE_PASSWORD`: the database password (type: Secret)
  - `STACKHOUSE_PUBLIC_HOST` = `stack-house-rust.vercel.app`: the address Supabase calls for reminders. It is kept on the permanent vercel.app address, so reminders don't depend on the GoDaddy record.

## What is live

| | |
|---|---|
| Family address | https://stackhouse.alsalemkuwait.com |
| Permanent Vercel address (same site) | https://stack-house-rust.vercel.app |
| Vercel project | `stack-house` (team mohammedalmutawaq-9247), region `sin1` |
| Supabase project | `kberxtxjetsyzbanwigf`, organisation Stack House (Free), region ap-southeast-1 |
| GoDaddy DNS | CNAME `stackhouse` → `fbc005998e262f3f.vercel-dns-016.com` |

## Steps (all done)

1. GitHub: create the empty private repository. ✅
2. Upload the code. ✅
3. Supabase: create a free organisation called **Stack House**. ✅
4. Supabase: create the project (Singapore). ✅
5. Supabase: reset the database password; copy the *Transaction pooler* address. ✅
6. Vercel: import `stack-house` from GitHub and add the environment variables above. ✅
7. Reminder timer: the app switches on `pg_net` and `pg_cron` by itself on its first production start. ✅ (Admin → Settings shows it green.)
8. Domain: added in Vercel; GoDaddy CNAME `stackhouse` added. ✅ Don't change any other GoDaddy record.
9. Admin account created. ✅ Next: add the people (Admin → People).
10. Test it — see the checklist below.

## Testing checklist (live)

Make two test accounts in **Admin → People**: `test-family` (a family member) and `test-chef` (Chef). Use two phones.

1. **Install the app on each phone.** Android/Chrome: ⋮ → *Install app*. iPhone/Safari: Share → *Add to Home Screen*, then open Stack House from the new icon.
2. **Me → Turn on notifications → Send a test** → a notification pops up.
3. As the family: **Plan → tomorrow → Save** → the chef's phone gets “🏠 … is set”.
4. As the family: **Order now** → the chef's phone (locked) shows “🚨 Order now”.
5. As the chef: **Accept**, then **Mark ready** → the family's phone gets “👨‍🍳 The kitchen is on it”, then “✅ Ready”.
6. **Admin → Settings** shows a green “Reminder timer is running”. Add a reminder time 3 minutes from now (before 22:00), using a family that hasn't planned tomorrow. That family gets the reminder within about a minute of that time. Remove the test time afterwards.
7. **Admin → Settings → Download backup** works.
8. Delete the test accounts.

Automatic check from any computer that isn't on the work network:

```bash
.venv\Scripts\python tools\smoke_test.py https://stackhouse.alsalemkuwait.com
```

## Updating later

Claude changes the code, commits and pushes, and Vercel redeploys automatically in about a minute. Data in Supabase is not affected.
