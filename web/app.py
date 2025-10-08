from flask import Flask, render_template, redirect, url_for, request
import subprocess, os, signal
from datetime import datetime

app = Flask(__name__)

# Basis-Pfade
# Basisverzeichnis ermitteln, egal wo app.py liegt
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Sub-Ordner definieren
bot_path = os.path.join(BASE_DIR, "strategies", "EMA_Touch", "bot.py")
configs_dir = os.path.join(BASE_DIR, "strategies", "EMA_Touch", "configs")
logs_dir = os.path.join(BASE_DIR, "strategies", "EMA_Touch", "logs")

print("BASE_DIR:", BASE_DIR)
print("Configs in:", configs_dir, "->", os.listdir(configs_dir))

process = None
current_config = None

@app.route("/", methods=["GET", "POST"])
def index():
    global process, current_config
    running = process is not None and process.poll() is None

    # Config-Dateien im Ordner "configs" einlesen (ohne base.yaml)
    available_configs = []
    if os.path.exists(configs_dir):
        available_configs = [
            f for f in os.listdir(configs_dir)
            if os.path.isfile(os.path.join(configs_dir, f))
            and f.endswith(".yaml")
            and f.lower() != "base.yaml"
        ]


    if request.method == "POST":
        # ausgewählte Config-Datei übernehmen
        selected_file = request.form.get("config")
        if selected_file:
            current_config = os.path.splitext(selected_file)[0]  # Name ohne .yaml

            if process is None or process.poll() is not None:
                # Log-Datei für die Config erstellen
                log_file = os.path.join(
                    logs_dir,
                    f"EMA_Touch_{current_config}_{datetime.now().strftime('%Y%m%d')}.log"
                )
                f = open(log_file, "a")
                process = subprocess.Popen(
                    ["python3", bot_path, "--config", current_config],
                    stdout=f, stderr=f, preexec_fn=os.setsid
                )
        return redirect(url_for("index"))

    # aktuelles Logfile für die Config laden
    logs = []
    if current_config:
        log_file = os.path.join(
            logs_dir,
            f"EMA_Touch_{current_config}_{datetime.now().strftime('%Y%m%d')}.log"
        )
        if os.path.exists(log_file):
            with open(log_file, "r") as f:
                logs = f.read().splitlines()[-49:]

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
