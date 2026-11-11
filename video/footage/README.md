# Live footage drop folder

Place the eight exact MP4 names from `../slots.json` here, then run `npm run build` from `video/`. Missing, invalid or undersized files fall back to the original README still with visible PLACEHOLDER and FOOTAGE labels. Normal builds never overwrite your inputs. `sourceIn` is an editable seconds offset in slots.json; duration must cover the complete slot. Source audio is muted in this edit.

Record at 30fps or higher. Guest-only slots can remain 640×480; whole-pane captures should be at least 1440×1000 for legible controls/logs. Keep the complete 4:3 guest visible. Never include credentials, tokens, environment files, private hostnames or network addresses. Trim on your side before copying; keep each file below 50 MB if committing it later.
