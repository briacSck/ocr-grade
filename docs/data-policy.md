# Privacy & your students' data

This tool handles scanned **student exams**, which are sensitive. Here's exactly
what stays on your Mac and what gets sent out, in plain terms.

## What never leaves your computer

- **The original scans** and the full-resolution page images.
- **Student names and IDs.** Before any page is transcribed, the app finds the
  name/ID area and **blacks it out**. The actual names and IDs are saved only in a
  private file on your Mac (used to name the output files) and are **never sent
  anywhere**.

## What gets sent for transcription

- **Only the blacked-out page image.** The version of the page that goes to the
  Mistral transcription service has the identity already covered with a solid black
  box. It's sent directly to the service for reading — not uploaded to any public
  link or shared store.
- **One small slice of the top of the page**, briefly, so the app can locate the
  name/ID in order to black it out. That slice is used only for that check.

That's it. The typed transcript that comes back is the only result, and it's kept
on your Mac.

## One thing to check before grading real exams

The transcription is done by **Mistral** (https://mistral.ai). Whether they keep
submitted images, and for how long, depends on your Mistral account settings and
their current terms, which can change. Before processing real student work:

- Review Mistral's privacy terms: https://mistral.ai/terms/#privacy-policy
- In your Mistral account, prefer settings with **no training on your data** and the
  **shortest retention** your plan offers.

When in doubt, treat anything sent to the service as leaving your custody — which is
why identity is blacked out on your computer first.

## Clean up when you're done

When you've finished grading and downloaded your transcripts, double-click
**`cleanup.command`** (see the README). It erases the uploaded scans and generated
transcripts from the computer. Anything you've already saved to your Downloads
folder is untouched.
