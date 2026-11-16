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
- **Vercel settings needed:** only `DATABASE_URL` (Supabase → **Connect** → *Transaction pooler*, pasted exactly as shown, including `[YOUR-PASSWORD]`) and `DATABASE_PASSWORD` (the database password).

## Steps

1. GitHub: create the empty private repository. ✅ done
2. Upload the code. ✅ done
3. Supabase: create a free organisation called **Stack House**.
4. Supabase: create the project in that organisation. ✅ done (Singapore)
5. Supabase: **Project Settings → Database → Reset database password** → copy the new password. Then click **Connect** (top of the project page) → **Transaction pooler** → copy the URI.
6. Vercel: **Add New → Project → Import** `stack-house`. Under **Environment Variables** add:
   - `DATABASE_URL` = the URI from step 5
   - `DATABASE_PASSWORD` = the password from step 5

   Then click **Deploy**.
7. Supabase timer: Claude turns on `pg_cron` and `pg_net` and schedules the one-minute call.
8. Domain:
   - Vercel → project → **Settings → Domains** → add `stackhouse.alsalemkuwait.com`.
   - GoDaddy → alsalemkuwait.com → **DNS → Add New Record**: type **CNAME**, name `stackhouse`, value exactly as Vercel shows it.
   - Don't change any other record.
9. On your phone (mobile data): open the site, create the admin account, and add the people.
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
