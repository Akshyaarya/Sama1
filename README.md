# Sama Cafe Online

Browser version starter for the existing Sama Cafe desktop software. It uses the existing Supabase PostgreSQL tables as the authoritative online database.

## Current online-ready features
- Admin/staff login using the existing `users` table
- Staff permissions using `user_permissions`
- Dashboard
- New billing with stock deduction
- Bill history and bill view
- Print bill
- WhatsApp bill link
- Current stock and stock receipt entry
- Customers
- Pending payments
- Sales report

## Important security
The server uses `SUPABASE_SECRET_KEY`. Keep this key only in Render Environment Variables. Never put it in HTML, JavaScript, GitHub, or screenshots. Supabase documents secret keys as server-side credentials that bypass RLS.

## Render deployment
1. Create a GitHub repository and upload this folder.
2. In Render choose **New -> Web Service**, connect the repo, select the **Free** plan.
3. Build command: `pip install -r requirements.txt`
4. Start command: `gunicorn app:app`
5. Add environment variables:
   - `FLASK_SECRET_KEY` = any long random secret
   - `SUPABASE_URL` = your Supabase project URL
   - `SUPABASE_SECRET_KEY` = your Supabase `sb_secret_...` key
6. Deploy.

The app does not store production data in SQLite; it reads/writes the Supabase database. The included SQLite fallback is only for local testing.

## Existing data
Your Supabase database should already contain the migrated tables/data. This project expects the same table/column names used by the existing Sama Cafe Python software.
