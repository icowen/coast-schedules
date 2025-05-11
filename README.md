# COAST Court Availability

To book a court at COAST, you need to wait for them to be "released" each Friday at a random time of the day.

This is very annoying and leads to favoritism (ie. manager can tell people right before they are released).

Especially when boys and girls teams are playing at the same time, court space can become very limited and hard to get.

This python script pulls the API from MindBody and alerts when any new court space opens up for the next week.

## Setup
1. Create a new virtual environment
```bash
python3 -m venv venv
source venv/bin/activate
```

2. Install requirements
```bash
pip3 install -r requirements.txt
```

3. Setup env file
- Add a new file named `.env` in the root of the repo
- It should contain:
```bash
USERNAME=<username to login to mindbody account>
PASSWORD=<password to login to mindbody account>

# These are optional. Uncomment if you want to use discord.
# DISCORD_CHANNEL_ID=<channel id to post to>
# DISCORD_TOKEN=<discord bot token>
```

4. Run the script
```bash
python3 main.py
```

If you want to run without posting to discord:
```bash
python3 main.py --no_discord
```