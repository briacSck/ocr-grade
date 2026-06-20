# Exam Transcriber

Turn scanned, handwritten exam PDFs into clean, typed transcripts you can read and
grade quickly. For each page you get the **original scan with a readable
transcription right next to it**, and each student's **name and ID are
automatically blacked out** before anything leaves your computer.

You run it on your own Mac through a simple web page in your browser. No coding.

---

## What you need

- A Mac.
- The **`ocr-grade` folder** on your computer (the one containing this README).
- A free **Mistral** account for the transcription service (you'll make one below).
- About **10 minutes**, once, for first-time setup.

---

## One-time setup (do this once)

### 1. Install the helper tool (`uv`)

Open the **Terminal** app (press `Cmd`+`Space`, type "Terminal", press Return).
Copy the line below, paste it into Terminal, and press Return:

```
curl -LsSf https://astral.sh/uv/install.sh | sh
```

When it finishes, **close the Terminal window**. (This installs a small tool the
app needs. You only do this once.)

### 2. Get your Mistral API key

1. Go to **https://console.mistral.ai/** and create an account (it's free to start).
2. Click **API Keys**, then **Create new key**.
3. **Copy the key now** — Mistral only shows it once. Paste it somewhere safe for a moment.

### 3. Enter your key and choose a password

In the `ocr-grade` folder there's a file called **`.env.example`**. We'll make your
own copy of it. In Terminal, paste these two lines one at a time:

```
cd ~/Downloads/ocr-grade        # change this if the folder is somewhere else
cp .env.example .env && open -e .env
```

A text editor opens your new **`.env`** file with three lines. Fill them in:

- `MISTRAL_API_KEY=` — paste the key you copied (right after the `=`, no spaces).
- `OCR_GRADE_WEB_USER=` — a username you'll use to log into the app (e.g. your name).
- `OCR_GRADE_WEB_PASSWORD=` — a password you choose for the app.

**Save** (`Cmd`+`S`) and close the editor. That's it — setup is done.

---

## Each time you grade exams

### 1. Start the app

Double-click **`start.command`** in the `ocr-grade` folder.

- A black Terminal window opens and stays open — **that's normal, leave it open.**
- Your browser opens the app a few seconds later. If it doesn't, go to
  **http://localhost:8000** yourself.
- The first time, your Mac may say the file is from an "unidentified developer."
  If so: **right-click `start.command` → Open → Open**. You only do that once.

### 2. Log in

Type the **username and password** you chose in your `.env` file.

### 3. Prepare your scans as a `.zip`

Put **one PDF per student** in a folder. In Finder, select all those PDFs,
right-click, and choose **Compress** — that makes a `.zip` file.

### 4. Upload and run

On the app page:

1. (Optional) Type your **course code** in the "Course override" box (e.g. `PE101`).
   It just labels the output files.
2. Click **Choose File** and pick your `.zip`.
3. Click **Start batch**.

The page shows progress and a running cost (transcription is a few tenths of a cent
per page). When it's done, **download** each transcript, or **Download all** as a
single `.zip`. The files save to your **Downloads** folder.

### 5. When you're finished — clean up

For your students' privacy, erase the scans and transcripts from the app when you're
done:

1. Make sure you've **downloaded** everything you want to keep.
2. **Close the black Terminal window** (this stops the app).
3. Double-click **`cleanup.command`**. It deletes the uploaded scans and generated
   transcripts from the computer. Anything already in your Downloads folder is kept.

---

## Privacy

Each student's name and ID are blacked out on your Mac **before** any page is sent
for transcription, and the names/IDs themselves are never sent. Only the
blacked-out page image goes to Mistral for reading. For the full details — and a
note to check your Mistral account's data settings before grading real exams — see
[docs/data-policy.md](docs/data-policy.md).

---

## Tips for the best transcripts

- **Scan clearly.** Scanning at about **300 DPI** gives noticeably better results.
  The current scans (~144 DPI) work, but higher resolution helps a lot.
- **Expect to glance at the original.** Messy handwriting, math symbols, and
  diagrams are hard for any transcription tool, so it can occasionally guess wrong.
  That's exactly why the original scan sits right next to the transcript — skim both.
- Paying for Mistral does **not** improve accuracy (it only raises how fast/how much
  you can run). Clearer, higher-resolution scans are what improve the transcript.

---

## If something goes wrong

| What you see | What to do |
| --- | --- |
| Double-clicking `start.command` does nothing | Right-click it → **Open** → **Open**. If still nothing, open Terminal, type `cd ` then drag the folder in, press Return, then run `bash start.command`. |
| "Web auth is not configured" | Your `.env` is missing the username/password. Re-open `.env` (step 3 of setup) and fill them in. |
| Login is rejected | The username/password must match your `.env` exactly. |
| "Unauthorized" / 401 error during a batch | Your Mistral key is missing or wrong in `.env`. Re-check it at https://console.mistral.ai/. |
| A transcript looks wrong | Compare it to the scan next to it; for messy handwriting this is expected. Rescanning that exam at higher resolution usually helps. |

Questions or a key that stopped working? Make a new key at
https://console.mistral.ai/ and paste it into your `.env`.
