from pathlib import Path
from flask import Flask, render_template, redirect, url_for, request
import subprocess, os, signal
from datetime import datetime

app = Flask(__name__)

# Verzeichnisse robust bestimmen
WEB_DIR   = Path(__file__).resolve().parent          # .../Bitunix_Trading_Bot/web
ROOT_DIR  = WEB_DIR.parent                           # .../Bitunix_Trading_Bot
STRAT_DIR = ROOT_DIR / "strategies" / "EMA_Touch"

bot_path     = STRAT_DIR / "bot.py"
configs_dir  = STRAT_DIR / "configs"
logs_dir     = STRAT_DIR / "logs"
logs_dir.mkdir(parents=True, exist_ok=True)

print("ROOT_DIR:", ROOT_DIR)
print("Configs in:", configs_dir, "->", list(configs_dir.glob("*.yaml")))

process = None
current_config = None

@app.route("/", methods=["GET", "POST"])
def index():
    global process, current_config
    running = process is not None and process.poll() is None

    # Config-Dateien (ohne base.yaml)
    available_configs = []
    if configs_dir.exists():
        available_configs = [
            p.name for p in configs_dir.glob("*.yaml")
            if p.name.lower() != "base.yaml"
        ]

    if request.method == "POST":
        selected_file = request.form.get("config")
        if selected_file:
            current_config = Path(selected_file).stem  # Name ohne .yaml
            if process is None or process.poll() is not None:
                log_file = logs_dir / f"EMA_Touch_{current_config}_{datetime.now().strftime('%Y%m%d')}.log"
                f = open(log_file, "a")
                process = subprocess.Popen(
                    ["python3", str(bot_path), "--config", current_config],
                    stdout=f, stderr=f, preexec_fn=os.setsid
                )
        return redirect(url_for("index"))

    logs = []
    if current_config:
        log_file = logs_dir / f"EMA_Touch_{current_config}_{datetime.now().strftime('%Y%m%d')}.log"
        if log_file.exists():
            with open(log_file, "r", errors="ignore") as f:
                logs = f.read().splitlines()


    return render_template("index.html",
                           running=running,
                           logs=logs,
                           config=current_config,
                           configs=available_configs)

@app.route("/stop")
def stop():
    global process, current_config
    if process and process.poll() is None:
        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
    process = None
    current_config = None
    return redirect(url_for("index"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
