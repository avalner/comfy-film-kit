# Direct YouTube publication

Use only when publication is requested or a standing instruction explicitly authorizes it. Accepting a frame, clip or final film alone does not authorize public posting. Existing authorization persists across chats; do not ask again for already approved unchanged video/metadata. No intermediary service, plugin, public file host or browser automation is needed.

## Persistent installation

Use the Python executable from assets/machine.json and scripts/youtube.py. Machine-local paths, verified channel and known playlists are in assets/youtube.json. This contains paths only, never credential contents. Libraries live permanently in $Tools/youtube-direct/dependencies, independent of any chat workspace. OAuth client and token live outside the kit, at the paths named by `client_secrets` and `token` in assets/youtube.json — never inside deliverables or skill packages. Never print, copy into outputs, commit, or bundle these secrets.

The configured channel comes from `channel_id`, `channel_title` and `channel_handle` in assets/youtube.json. Verify using `account` before publishing. Existing refresh credentials normally avoid interactive login; if expired/revoked or scopes missing, run `auth` (with `--manage-playlists` when needed). The user completes Google login/consent. A wrong channel stops the operation. For access_denied in Testing, add the login email under Google Auth Platform → Audience → Test users; test grants may expire after seven days. Do not claim OAuth approval guarantees public uploads; check actual returned visibility and processing.

**Sandbox caveat.** The first API call refreshes the token and rewrites the `token` file named in assets/youtube.json. Under DSH's workspace-write policy that write is outside the workspace, so `account`/`upload` die with a bare `PermissionError` before any request is made — it looks like broken auth but it is the token write. Run those commands with full-disk access (one approval), or refresh the token outside the sandbox first. The upload journal lives inside the project and needs no extra access.

In DSH there is no drafting sub-agent step: write the metadata package in the parent, save it to `youtube.json`, and show the complete title and description for explicit approval. The parent retains live metadata, user approvals and all publication operations.

## Review and metadata

Select the exact final export the user approved, including any accepted seam/trim fixes, not an older review or export. Store `youtube.json` in the project with title, description, tags, categoryId (string), language, privacyStatus, madeForKids (boolean), containsSyntheticMedia (boolean), notifySubscribers (boolean), playlistIds (array), source file and approval note. Default preferred language is English; reuse explicit preferences. Audience and playlist choices are project-specific: ask only if missing, never infer made-for-kids solely from a cute character. Offer matching existing playlists from `playlists`; reuse an explicit existing choice. Do not create new playlists unless asked.

Before uploading new or changed metadata, show a publication preview in chat from the exact saved `youtube.json`: the full title and the complete description, including every paragraph, link and hashtag, with their actual line breaks. Label title and description separately; use a text block for the description so it is easy to read and copy. Do not replace either with a summary, excerpt or a separate approximate list of hashtags. Also identify the exact accepted video/version, channel, visibility, audience, playlist, AI disclosure and subscriber notification setting. This preview is a normal chat message — never text inside the question card (SKILL.md non-negotiable 9).

After showing the preview, ask through the menu tool with the bare labels **Публикуем / Изменить название или описание / Отмена** (or the user’s language), and wait for an explicit reply before `upload`. The question itself is one short sentence; the title, the description and the settings stay in the message above it. A request such as “publish to YouTube” authorizes preparing this package; it does not approve newly drafted text. If the user requests edits, save them and show the complete updated title and description for approval. Do not silently change approved text. Record metadata approval in project `youtube.json`; `--approved` represents actual user authorization.

Reuse existing approval for the exact unchanged package without asking again. Explicit delegation to choose and publish metadata also remains valid; show the exact final title and description as an informational preview before uploading, without adding an approval gate the user waived.

## Commands

```powershell
python scripts/youtube.py account
python scripts/youtube.py playlists
python scripts/youtube.py auth --manage-playlists
python scripts/youtube.py upload --project PROJECT --file APPROVED_FINAL.mp4 --metadata PROJECT/youtube.json --approved
python scripts/youtube.py status --project PROJECT --wait 180
python scripts/youtube.py add-playlist --video VIDEO_ID --playlist 'My Playlist'
```

`upload` saves PROJECT/.pipeline/youtube-upload.json before submission; it records the source hash, video ID and response. Existing journals block re-upload across chats, even if the file was edited: inspect/status first. Preserve the journal and prior exports. Do not delete/reset a journal to retry an uncertain upload; recover the recorded resumable session or check the channel before any new submission. Treat any resumable_uri in the journal as sensitive; do not display or copy it to a public deliverable. Do not automatically retry a non-idempotent upload.

`status --wait` is a local persistent wait, not a model polling loop; await its same terminal session. Report uploaded/processing separately from processed/succeeded, and verify privacyStatus really matches the requested visibility. Then add each selected playlist. Playlist insertion checks ownership and existing membership by listing full contents, and verifies by item ID to tolerate indexing delay. On an uncertain insertion, inspect the playlist before inserting again. A playlist failure does not justify another video upload.

After success, save video URL, ID, actual privacy/processing, selected playlist IDs and membership verification in project youtube.json/brief.md. Return the actual YouTube link and any unresolved limitation. The same settings and journal let another chat resume without reading chat history.
