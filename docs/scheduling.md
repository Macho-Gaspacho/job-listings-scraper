# Run the search every day

This runs the normal search on your computer. It writes `output/jobs.xlsx` and does not upload anything.

Run the program once by hand first, so `config.yaml` and `.venv` already exist. Then schedule that same start file.

The pictures below are placeholders. Replace each file with a screenshot of your own screen, and do not include a real job search in the picture.

## Windows Task Scheduler

This starts `start.bat` every day.

1. Press the Windows key and type **Task Scheduler**. Open it.
2. In the right-hand list, click **Create Basic Task**.
3. Name it `Job search`. Click Next.
4. Choose **Daily**. Click Next. Pick a time when the computer is usually on, such as 08:00. Click Next.
5. Choose **Start a program**. Click Next.
6. In **Program/script**, put the full path to `start.bat`. Example: `C:\Users\you\job-listings-scraper\start.bat`
7. In **Start in**, put the project folder, without quotes. Example: `C:\Users\you\job-listings-scraper`
8. Click Next, then Finish.
9. The new task is in Task Scheduler Library. Right-click it and choose **Run** once, to check that a window opens and the search finishes.

`start.bat` ends with `pause`, so the window waits for a key. In the task's properties, on the General tab, leave **Run only when user is logged on** selected. You will see the window and can press a key at the end.

If you want the task to finish with nobody at the keyboard, set the program to `C:\Windows\System32\cmd.exe` and the arguments to `/c "start.bat < nul"`. Keep **Start in** as the project folder. The `< nul` part lets `pause` finish.

![Placeholder: the Create Basic Task window, with start.bat as the program](img/windows-task-scheduler.png)

## Mac: Calendar

This opens `start.command` in Terminal, the same as a double-click.

1. Open **Calendar**.
2. Create an event named `Job search`. Set it to repeat **Every day**, at a time the Mac is usually awake.
3. Add an alert. Choose **Custom**, then **Open file**, and select `start.command` in the project folder.
4. Save the event. At that time Terminal opens and the search runs. Press Enter when it asks, to close the window.

![Placeholder: a daily Calendar event whose alert opens start.command](img/macos-calendar.png)

## Mac: launchd

Use this when you want the search to run even if Calendar is not the tool you prefer. `start.command` runs `start.sh`. Under launchd there is no keyboard, so the final "Press Enter" line finishes on its own.

1. Create the folder `~/Library/LaunchAgents` if it does not exist.
2. Save the text below as `~/Library/LaunchAgents/com.example.job-listings-scraper.plist`. Replace both `/Users/YOU/job-listings-scraper` paths with your own folder.
3. In Terminal, run:

```bash
launchctl load ~/Library/LaunchAgents/com.example.job-listings-scraper.plist
```

4. To check it once, without waiting until 08:00:

```bash
launchctl start com.example.job-listings-scraper
```

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.example.job-listings-scraper</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>/Users/YOU/job-listings-scraper/start.command</string>
  </array>
  <key>WorkingDirectory</key>
  <string>/Users/YOU/job-listings-scraper</string>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>
    <integer>8</integer>
    <key>Minute</key>
    <integer>0</integer>
  </dict>
</dict>
</plist>
```

The log, if you want one, can be added later with `StandardOutPath` and `StandardErrorPath` keys pointing at files inside the project folder. Do not point them at a public place.

## Linux: cron

Cron runs `start.sh`. There is no keyboard, so the final "Press Enter" line finishes on its own.

1. Open a terminal in the project folder and run `crontab -e`.
2. Add one line. Use the real path to the project. This example runs at 08:00 every day:

```cron
0 8 * * * cd /home/you/job-listings-scraper && ./start.sh >> /home/you/job-listings-scraper/output/cron.log 2>&1
```

3. Save and close the editor. `crontab -l` should show the line.
4. The first time, run `./start.sh` yourself so `.venv` exists. Cron will not install Python for you.

`output/` is gitignored. The log stays on your computer.

![Placeholder: a terminal showing crontab -l with the daily line](img/linux-cron.png)

## What this does not do

Scheduling does not commit or push. Your roles, cities, and seen listings stay on this computer.

A separate script, `examples/automation/daily_git_commit.py`, can publish those files with git. **Only use it with a private repo. It publishes your job search history.** It refuses to push unless `config.yaml` contains:

```yaml
daily_git:
  enabled: true
  i_understand_this_is_public_if_repo_is_public: true
```

Leave that block out for a normal daily search.
