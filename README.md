# Soccer Player Picker — Setup Guide

A team web tool that automatically ranks soccer players for your YouTube channel based on **YouTube content gap** (how few animated bios exist) and **Google Trends momentum** (rising search interest), plus YouTube search demand. Story and skill scores are still manual sliders.

You don't need to know how to code. Setup takes about 30 minutes the first time. After that, your team just opens a URL.

---

## What you'll end up with

- A web app at `https://your-name.streamlit.app` that your whole team can use.
- Free hosting (Streamlit Community Cloud).
- Free API usage (well within Google's free tier for weekly use).
- One-click CSV export for sharing rankings.

---

## What you need

1. A Google account (for the API key).
2. A GitHub account ([sign up free](https://github.com/signup) if you don't have one).
3. A Streamlit Cloud account (sign up with your GitHub account).

---

## Step 1 — Get a free YouTube API key (5 min)

1. Go to **https://console.cloud.google.com/**.
2. Sign in with your Google account.
3. At the top, click the project dropdown → **New project**. Name it `soccer-picker`. Click Create.
4. Wait ~30 seconds for it to finish, then make sure `soccer-picker` is selected in the project dropdown.
5. In the search bar at the top, type `YouTube Data API v3` and click the result.
6. Click the blue **Enable** button. Wait a few seconds.
7. In the left sidebar, click **Credentials**.
8. Click **+ Create credentials** at the top → **API key**.
9. A box pops up with your key. **Copy it and save it somewhere safe** (a notes app is fine). It looks like `AIzaSyB...` and is about 39 characters long.
10. Click **Close**.

> Optional but recommended: click your new API key in the credentials list → under "API restrictions" select "Restrict key" → check only "YouTube Data API v3" → Save. This makes the key safer.

---

## Step 2 — Put the code on GitHub (5 min)

1. Go to **https://github.com/new**.
2. Repository name: `soccer-picker`. Keep it **Public** (private also works on free Streamlit Cloud now, public is simpler).
3. Click **Create repository**.
4. On the new repo page, click **uploading an existing file** (in the quick-setup section).
5. Drag these three files from the `soccer-picker/` folder into the upload area:
   - `app.py`
   - `requirements.txt`
   - `README.md` (this file)
6. Scroll down and click **Commit changes**.

---

## Step 3 — Deploy to Streamlit Cloud (5 min)

1. Go to **https://share.streamlit.io/** and click **Sign in with GitHub**. Authorize when asked.
2. Click **Create app** → **Deploy a public app from GitHub**.
3. Fill in:
   - **Repository**: `your-github-username/soccer-picker`
   - **Branch**: `main`
   - **Main file path**: `app.py`
   - **App URL**: pick something memorable, e.g. `soccer-picker-yourteam`
4. **Before clicking Deploy**, click **Advanced settings**.
5. In the **Secrets** box, paste this (replace the placeholder with your actual key from Step 1):

   ```toml
   YOUTUBE_API_KEY = "paste-your-AIzaSy...-key-here"
   ```

6. Click **Save**, then **Deploy**.
7. Wait 1–3 minutes for the first build. You'll see a log scroll by. When it's done, your app is live.

---

## Step 4 — Share with your team

Send your team the URL: `https://soccer-picker-yourteam.streamlit.app` (whatever you picked).

By default the app is public — anyone with the link can use it. That's usually fine since there's nothing sensitive. If you want to restrict access:

- In Streamlit Cloud, open your app → **Settings** → **Sharing** → enable viewer authentication and add specific Google emails to the allowlist.

---

## How to use the app

1. Open the URL.
2. In the text box, list 5–10 player names (one per line).
3. Click **Analyze players**. Wait ~10–30 seconds while it pulls data from YouTube and Google Trends.
4. See the winner at the top with the auto-generated reason.
5. Expand each player to adjust **story richness** and **teachable skill** manually (these can't be auto-scored).
6. Click **Download as CSV** to save the rankings.

---

## Limits to know about

- **YouTube API daily quota**: ~50 unique players per day on the free tier. Cached results don't count against this, so re-running the same players within an hour is free.
- **Google Trends**: This uses an unofficial library that Google sometimes rate-limits. If a player gets a default score of 5 with a warning, that's why — wait 10 minutes and try again, or upgrade to a paid trends service later.
- **Streamlit free tier**: The app sleeps after a week of zero traffic but wakes up in ~30 seconds when someone visits.

---

## Customizing

To change the weights, open `app.py` on GitHub, click the pencil icon, and edit the `WEIGHTS` dictionary near the top:

```python
WEIGHTS = {
    "contentGap": 0.35,      # change these numbers
    "googleTrends": 0.30,    # they must add up to 1.0
    "ytSearchDemand": 0.15,
    "storyRichness": 0.10,
    "skillTeachable": 0.10,
}
```

Commit the change and Streamlit Cloud will auto-redeploy in ~1 minute.

---

## Troubleshooting

**"YouTube API key not configured"** — You skipped Step 3.5. In Streamlit Cloud, open your app → Settings → Secrets and add `YOUTUBE_API_KEY = "..."`.

**"YouTube API error: quotaExceeded"** — You've used today's free quota (~50 player analyses). It resets at midnight Pacific time.

**Google Trends scores all default to 5** — Google's rate-limited your app's IP. Wait 10–15 minutes, or analyze fewer players at a time.

**App is slow to load first time** — Streamlit Cloud put it to sleep after a week. First visit wakes it up in 30 seconds.

---

## Need to make changes?

Edit `app.py` on GitHub, commit, and Streamlit redeploys automatically. No re-deployment commands needed.
