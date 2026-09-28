# Encrypted SQLite backups to the owner's private Telegram chat

This is a second, independent database backup in addition to the VPS provider's
daily full-machine restore point. It backs up **only** `/data/bot.sqlite3`, not
`.env`, media files, downloads or logs. The bot and API remain online while
SQLite's backup API creates a consistent copy. The copy is checked with
`PRAGMA quick_check`, gzip-compressed, encrypted with `age`, and only then sent
using Telegram `sendDocument`. Plaintext temporary files are removed after the
send. A failure is logged by systemd and, when Telegram is reachable, reported
as a private message to the owner.

Never put the private decryption key on the VPS, in Git, or in Telegram. Preserve
it on two independent devices or offline media: without it, the backups cannot
be restored. Do not send `.env` or an unencrypted database to Telegram.

## One-time setup

1. From Windows PowerShell, create a **dedicated** passphrase-protected key:

   ```powershell
   ssh-keygen -t ed25519 -f "$env:USERPROFILE\.ssh\otveto4ka-backup" -C otveto4ka-backup
   ```

   Back up the private file `otveto4ka-backup` securely outside the VPS.

2. Copy **only the `.pub` file** to the VPS, authenticating with the separate
   VPS SSH login key:

   ```powershell
   scp -i "$env:USERPROFILE\.ssh\otveto4ka-vps-2026-09-28" "$env:USERPROFILE\.ssh\otveto4ka-backup.pub" debian@51.195.40.188:/home/debian/backup-recipient.pub
   ```

3. On the VPS, from `/home/debian/otveto4ka-current`:

   ```sh
   sudo apt-get update
   sudo apt-get install -y age
   sudo install -d -m 0700 /etc/otveto4ka-backup
   sudo install -m 0644 /home/debian/backup-recipient.pub /etc/otveto4ka-backup/recipient.pub
   sudo python3 server-telegram-backup.py --check
   sudo python3 server-telegram-backup.py
   ```

   `OWNER_ID` in the existing `.env` must be the numeric ID of the intended
   private chat. The owner must have started the bot. The script checks the
   Telegram chat type and ID before uploading. Do not paste `.env` or the bot
   token into a chat or terminal output.

4. Confirm that the first **`.sqlite3.gz.age`** document arrived in the private
   chat. Download it to Windows and test decrypting and checking the database
   before enabling the timer. Install `age` on Windows from its official
   [release page](https://github.com/FiloSottile/age/releases), then:

   ```powershell
   age -d -i "$env:USERPROFILE\.ssh\otveto4ka-backup" -o "$env:TEMP\otveto4ka-test.sqlite3.gz" "$env:USERPROFILE\Downloads\otveto4ka-db-DATE.sqlite3.gz.age"
   python -c "import gzip,sqlite3,tempfile,pathlib; p=pathlib.Path(tempfile.gettempdir())/'otveto4ka-test.sqlite3'; p.write_bytes(gzip.decompress((pathlib.Path(tempfile.gettempdir())/'otveto4ka-test.sqlite3.gz').read_bytes())); c=sqlite3.connect(p); print(c.execute('PRAGMA quick_check').fetchone()[0]); c.close()"
   ```

   Replace the example downloaded filename with the actual one. The result
   should be `ok`. Keep the downloaded encrypted copy; securely handle the
   temporary decrypted files.

5. Enable the daily systemd timer:

   ```sh
   sh server-install-telegram-backup.sh
   sudo systemctl list-timers --all otveto4ka-telegram-backup.timer
   sudo journalctl -u otveto4ka-telegram-backup.service -n 30 --no-pager
   ```

It runs at 03:15 UTC with up to 15 minutes of random delay and catches up after
missed runs. Each message has a unique UTC timestamp; no prior Telegram message
is overwritten or automatically deleted. At the current database size this
requires little space, but monitor growth. The script refuses documents above
45 MiB (safely below the standard Bot API 50 MB upload limit) and reports a
failure rather than silently truncating the backup.

The VPS provider's single daily restore point and these Telegram documents are
different recovery options. Neither protects against losing the private key or
the Telegram account. Periodically repeat the decryption test on a recent file.
