from pathlib import Path
from flask import Flask, render_template, redirect, url_for, request, jsonify
import subprocess, os, signal, sys
from datetime import datetime

app = Flask(__name__)

# Verzeichnisse robust bestimmen
WEB_DIR   = Path(__file__).resolve().parent          # .../Bitunix_Trading_Bot/web
ROOT_DIR  = WEB_DIR.parent                           # .../Bitunix_Trading_Bot
STRAT_DIR = ROOT_DIR / "strategies" / "GRID"

bot_path    = STRAT_DIR / "bot.py"
configs_dir = STRAT_DIR / "configs"
logs_dir    = STRAT_DIR / "logs"
logs_dir.mkdir(parents=True, exist_ok=True)

print("ROOT_DIR:", ROOT_DIR)
print("Configs in:", configs_dir, "->", list(configs_dir.glob("*.yaml")))

# venv-Interpreter der laufenden Web-App verwenden
PYTHON = Path(sys.executable)  # zeigt auf .../.venv/bin/python
if not PYTHON.exists():        # Fallback (theoretisch)
    PYTHON = ROOT_DIR / ".venv" / "bin" / "python"

process = None
current_config = None

@app.route("/", methods=["GET", "POST"])
def index():
    global process, current_config
    running = process is not None and process.poll() is None

    # verfügbare Configs (ohne base.yaml)
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

            # Nur starten, wenn nichts läuft
            if process is None or process.poll() is not None:
                log_file = logs_dir / f"EMA_Touch_{current_config}_{datetime.now().strftime('%Y%m%d')}.log"

                # Subprozess im venv starten, Logs anhängen
                env = os.environ.copy()
                env["PYTHONUNBUFFERED"] = "1"  # sofortiges Logging
                with open(log_file, "a") as f:
                    process = subprocess.Popen(
                        [str(PYTHON), str(bot_path), "--config", current_config],
                        stdout=f, stderr=f, preexec_fn=os.setsid, env=env
                    )
        return redirect(url_for("index"))

    # aktuelles Log lesen (ohne Limit)
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


@app.route("/logs")
def get_logs():
    global current_config
    logs = []
    if current_config:
        log_file = logs_dir / f"EMA_Touch_{current_config}_{datetime.now().strftime('%Y%m%d')}.log"
        if log_file.exists():
            with open(log_file, "r", errors="ignore") as f:
                logs = f.read().splitlines()
    return jsonify({"logs": logs})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
