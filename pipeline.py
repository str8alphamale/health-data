import requests, base64, json, os, subprocess
from datetime import date, timedelta

CLIENT_ID = "23VJDN"
TOKEN_FILE = os.path.expanduser("~/.fitbit_tokens.json")
SECRET_FILE = os.path.expanduser("~/.fitbit_secret")
REPO_DIR = os.path.expanduser("~/health-data")

def load_secret():
    with open(SECRET_FILE) as f:
        return f.read().strip()

def load_tokens():
    with open(TOKEN_FILE) as f:
        return json.load(f)

def save_tokens(tokens):
    with open(TOKEN_FILE, "w") as f:
        json.dump(tokens, f, indent=2)
    os.chmod(TOKEN_FILE, 0o600)

def refresh_token(tokens, secret):
    credentials = base64.b64encode(f"{CLIENT_ID}:{secret}".encode()).decode()
    r = requests.post("https://api.fitbit.com/oauth2/token",
        headers={"Authorization": f"Basic {credentials}", "Content-Type": "application/x-www-form-urlencoded"},
        data={"grant_type": "refresh_token", "refresh_token": tokens["refresh_token"]})
    if r.status_code != 200:
        print("Token refresh mislukt:", r.json())
        exit(1)
    new_tokens = r.json()
    save_tokens(new_tokens)
    return new_tokens

def fitbit_get(path, token):
    r = requests.get(f"https://api.fitbit.com{path}",
        headers={"Authorization": f"Bearer {token}"})
    if r.status_code == 401:
        return None
    if not r.text.strip():
        return {}
    try:
        return r.json()
    except Exception:
        return {}

def get_data_for_date(day_str, tokens, secret):
    token = tokens["access_token"]
    sleep = fitbit_get(f"/1.2/user/-/sleep/date/{day_str}.json", token)
    if sleep is None:
        tokens = refresh_token(tokens, secret)
        token = tokens["access_token"]
        sleep = fitbit_get(f"/1.2/user/-/sleep/date/{day_str}.json", token)
    steps = fitbit_get(f"/1/user/-/activities/date/{day_str}.json", token)
    hrv = fitbit_get(f"/1/user/-/hrv/date/{day_str}.json", token)
    hr = fitbit_get(f"/1/user/-/activities/heart/date/{day_str}/1d.json", token)

    d = {}
    if sleep and sleep.get("sleep"):
        m = sleep["sleep"][0]
        d["slaap_min"] = m.get("minutesAsleep", "?")
        d["slaap_diep"] = m.get("levels", {}).get("summary", {}).get("deep", {}).get("minutes", "?")
        d["slaap_rem"] = m.get("levels", {}).get("summary", {}).get("rem", {}).get("minutes", "?")
    else:
        d["slaap_min"] = d["slaap_diep"] = d["slaap_rem"] = "?"
    if steps:
        d["stappen"] = steps.get("summary", {}).get("steps", "?")
        d["kcal_verbrand"] = steps.get("summary", {}).get("caloriesOut", "?")
        d["actieve_min"] = steps.get("summary", {}).get("fairlyActiveMinutes", 0) + steps.get("summary", {}).get("veryActiveMinutes", 0)
    if hrv and hrv.get("hrv"):
        d["hrv"] = hrv["hrv"][0].get("value", {}).get("dailyRmssd", "?")
    else:
        d["hrv"] = "?"
    if hr:
        d["rusthartslag"] = hr.get("activities-heart", [{}])[0].get("value", {}).get("restingHeartRate", "?")
    else:
        d["rusthartslag"] = "?"
    return d, tokens

def build_snapshot(day_str, d):
    return f"""# Health Snapshot — {day_str}

## Slaap
- Totaal: {d.get('slaap_min','?')} min
- Diep: {d.get('slaap_diep','?')} min
- REM: {d.get('slaap_rem','?')} min

## Hartslag & HRV
- Rusthartslag: {d.get('rusthartslag','?')} bpm
- HRV (RMSSD): {d.get('hrv','?')} ms

## Beweging
- Stappen: {d.get('stappen','?')}
- Actieve minuten: {d.get('actieve_min','?')}
- Calorieën verbrand: {d.get('kcal_verbrand','?')}

## Voeding (Cronometer)
*(voeg handmatig toe of upload cronometer_export.csv)*

## Bloedwaarden
*(handmatig invullen na bloedtest)*
"""

def get_existing_dates():
    dates = set()
    for f in os.listdir(REPO_DIR):
        if f.startswith("snapshot_") and f.endswith(".md"):
            dates.add(f.replace("snapshot_","").replace(".md",""))
    return dates

def git_push():
    os.chdir(REPO_DIR)
    subprocess.run(["git", "add", "."])
    subprocess.run(["git", "commit", "-m", f"snapshot {date.today().isoformat()}"])
    subprocess.run(["git", "push"])
    print("Gepusht naar GitHub")

def main():
    secret = load_secret()
    tokens = load_tokens()
    existing = get_existing_dates()
    today = date.today()
    changed = False
    for i in range(1, 31):
        day = today - timedelta(days=i)
        day_str = day.isoformat()
        if day_str not in existing:
            print(f"Ophalen: {day_str}")
            data, tokens = get_data_for_date(day_str, tokens, secret)
            snapshot = build_snapshot(day_str, data)
            path = os.path.join(REPO_DIR, f"snapshot_{day_str}.md")
            with open(path, "w") as f:
                f.write(snapshot)
            changed = True
    if changed:
        git_push()
    else:
        print("Alles up-to-date")

if __name__ == "__main__":
    main()
