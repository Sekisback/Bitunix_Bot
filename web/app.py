import os, subprocess, signal
from flask import Flask, render_template, redirect, url_for
from datetime import datetime

app = Flask(__name__)

# Pfad zur Strategie absolut auflösen
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
strategy_path = os.path.join(BASE_DIR, "strategies", "strategy_ema21touch.py")

# Logfile (aktuelles Tageslog)
logfile = os.path.join(BASE_DIR, "logs", f"bot_{datetime.now().strftime('%Y%m%d')}.log")

process = None

@app.route("/")
def index():
    global process
    running = process is not None and process.poll() is None

    logs = []
    if os.path.exists(logfile):
        with open(logfile, "r") as f:
            logs = f.read().splitlines()[-50:]

    return render_template("index.html", running=running, logs=logs)

@app.route("/start")
def start():
    global process
    if process is None or process.poll() is not None:
        f = open(logfile, "a")
        process = subprocess.Popen(
            ["python3", strategy_path],
            stdout=f, stderr=f, preexec_fn=os.setsid
        )
    return redirect(url_for("index"))

@app.route("/stop")
def stop():
    global process
    if process and process.poll() is None:
        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
    process = None
    return redirect(url_for("index"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
