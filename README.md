# nethack-char

Rerolls NetHack characters on a dgamelaunch server over SSH until the starting stats meet your minimums. A matching character is saved; anything else is quit and a new one is rolled.

## How it works

1. Connects over SSH and logs in to dgamelaunch by passing `DGLAUTH=<user>:<password>` (the same as `ssh -o SetEnv=DGLAUTH=...`).
2. Presses `p` (play) and `y` (accept the character).
3. Reads `St Dx Co In Wi Ch` from the status line and compares them with `min_stats`.
4. **Stats met:** saves the game (`S`, `y`), leaves dgamelaunch and disconnects.
5. **Stats not met:** quits the game (`#q`, `y`), goes back to the dgamelaunch menu and rolls again over the same connection.

The role, race, gender and alignment come from your NetHack options on the server, so set those there first (for example `OPTIONS=role:Monk,race:human`).

## Requirements

- Python 3.14+ and [uv](https://docs.astral.sh/uv/)
- The server must already be in `~/.ssh/known_hosts`. Unknown hosts are rejected, so connect once with plain `ssh` first.
- The Race etc must be predefined in `options`

## Setup

```sh
uv sync
cp config.example.json config.json
```

Edit `config.json`:

| Key | Description |
|---|---|
| `host`, `port` | SSH server address |
| `username` | SSH user |
| `key_filename` | Optional SSH private key. Leave it out to use only your SSH agent or a password. |
| `nethack_user` | dgamelaunch / NetHack account name |
| `max_attempts` | Number of characters to roll before giving up. `0` = keep going until the stats are met. |
| `min_stats` | Minimum value per stat (`St`, `Dx`, `Co`, `In`, `Wi`, `Ch`). Stats that are left out aren't checked. Exceptional strength is written as a string, e.g. `"St": "18/50"`. |

Example:

```json
"min_stats": { "St": 16, "Dx": 14, "Co": 11, "Wi": 16 }
```

## Running

```sh
uv run nethack-char config.json
```

You are prompted for the NetHack password unless `NETHACK_PASSWORD` is set:

```sh
NETHACK_PASSWORD=... uv run nethack-char config.json
```

### SSH password login

By default SSH uses your key or SSH agent. To log in with a password instead:

```sh
uv run nethack-char config.json --ssh-password    # prompts for the SSH password
SSH_PASSWORD=... uv run nethack-char config.json  # no prompt
```

### Output

Each roll is printed, for example:

```
Attempt 1: St:16 Dx:14 Co:13 In:10 Wi:14 Ch:8 -> not OK
Game quit.
Attempt 2: St:16 Dx:15 Co:12 In:8 Wi:16 Ch:8 -> OK
Game saved.
```

Exit code is `0` when a character was saved and `1` when `max_attempts` was reached without a match. Press Ctrl+C to stop at any time.

## Troubleshooting

- **Timed out waiting for ...**: the screen didn't look as expected. The message includes the current screen. A common cause is an existing saved game, which `p` resumes instead of starting a new character.
- **Server not found in known_hosts**: run `ssh -p <port> <user>@<host>` once and accept the host key.
- Keep `config.json` and any recordings out of git. Both are listed in `.gitignore`.
