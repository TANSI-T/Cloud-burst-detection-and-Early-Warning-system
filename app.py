from flask import Flask, jsonify, send_from_directory, request, send_file
from flask_cors import CORS
from flask_socketio import SocketIO
import sqlite3
import os
import time
from urllib import request as urlrequest
from urllib import error as urlerror
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split

# -------------------------------
HARDWARE_MODE = True
ESP32_TIMEOUT_SECONDS = 15
EMERGENCY_PING_URL = "http://10.163.230.174:8081/bm"
INTRO_VIDEO_PATH = r"C:\Users\Tansi\Downloads\WhatsApp Video 2026-05-06 at 10.12.19 PM.mp4"
DB_PATH = os.getenv("CLOUDBURST_DB_PATH", "cloudburst_project.db")
# -------------------------------

app = Flask(__name__)
CORS(app, origins="*")
socketio = SocketIO(app, cors_allowed_origins="*")
last_esp32_seen_ts = 0.0
relay_command_state = {"r1": 0, "r2": 0, "r3": 0}

# -------------------------------
# LOAD MODEL
# -------------------------------
df = pd.read_csv("cloudburst_15stage_dataset.csv")
X = df[["rainfall", "humidity", "pressure", "temperature"]]
y = df["label_num"]
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
model = RandomForestClassifier(n_estimators=100, random_state=42)
model.fit(X_train, y_train)

label_map = {
    0:"Clear Weather", 1:"Cloud Formation", 2:"High Humidity",
    3:"Light Rain", 4:"Moderate Rain", 5:"Heavy Rain Start",
    6:"Heavy Rain", 7:"Very Heavy Rain", 8:"Intense Rainfall",
    9:"Extreme Rain", 10:"Critical Rainfall", 11:"Severe Rainfall",
    12:"Extreme Weather", 13:"Near Cloudburst", 14:"Cloudburst Stage"
}

def get_alert_level(stage):
    if stage >= 14: return "CRITICAL"
    elif stage >= 12: return "HIGH"
    elif stage >= 9: return "WARNING"
    elif stage >= 5: return "MODERATE"
    else: return "NORMAL"

# -------------------------------
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS sensor_readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sensor_id TEXT NOT NULL,
            rain_intensity REAL,
            duration REAL,
            cloudburst INTEGER DEFAULT 0,
            local_alert INTEGER DEFAULT 0,
            sms_sent INTEGER DEFAULT 0,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS alert_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stage_num INTEGER,
            stage_name TEXT,
            rainfall REAL,
            humidity REAL,
            pressure REAL,
            temperature REAL,
            alert_message TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()
    cursor.close()
    conn.close()


def safe_get_db():
    try:
        return get_db()
    except Exception as db_error:
        print("[WARN] DB connection unavailable:", db_error)
        return None


def clamp_relay_value(value):
    return 1 if str(value) == "1" else 0

# -------------------------------
# DASHBOARD
# -------------------------------
@app.route('/')
def home():
    return send_from_directory('.', 'splash.html')

@app.route('/dashboard')
def dashboard():
    return send_from_directory('.', 'cloudburst_dashboard (3).html')

@app.route('/intro-video')
def intro_video():
    return send_file(INTRO_VIDEO_PATH, mimetype='video/mp4')

# -------------------------------
# RECEIVE DATA FROM ESP32
# -------------------------------
@app.route('/data', methods=['POST'])
def receive_data():
    try:
        global last_esp32_seen_ts

        data = request.json or {}
        print("[DATA] ESP32 Raw Data:", data)

        # Treat payloads with relay/soil fields as real ESP32 telemetry.
        device_source = "esp32" if any(k in data for k in ("relay1", "relay2", "relay3", "soil")) else "web"
        if device_source == "esp32":
            last_esp32_seen_ts = time.time()

        # Map values properly.
        rainfall = float(data.get("rain", data.get("rainfall", data.get("rain_intensity", 0))))
        humidity = float(data.get("humidity", 0))
        pressure = float(data.get("pressure", 0))
        temperature = float(data.get("temperature", data.get("temp", 0)))

        # ---------------- PREDICT STAGE ----------------
        input_data = pd.DataFrame([[rainfall, humidity, pressure, temperature]],
                                   columns=["rainfall", "humidity", "pressure", "temperature"])
        stage_num = int(model.predict(input_data)[0])
        stage_name = label_map[stage_num]
        alert_level = get_alert_level(stage_num)

        # ---------------- DB SAVE ----------------
        if HARDWARE_MODE:
            try:
                conn = safe_get_db()
                if conn is not None:
                    cursor = conn.cursor()

                    query = """INSERT INTO sensor_readings 
                               (sensor_id, rain_intensity, duration, cloudburst, local_alert, sms_sent)
                               VALUES (?, ?, ?, ?, ?, ?)"""
                    cloudburst = 1 if stage_num >= 14 else 0
                    local_alert = 1 if stage_num >= 9 else 0
                    sms_sent = 1 if stage_num >= 12 else 0
                    cursor.execute(query, ('SENSOR_01', rainfall, temperature, cloudburst, local_alert, sms_sent))

                    conn.commit()
                    cursor.close()
                    conn.close()
            except Exception as db_error:
                print("[ERROR] DB Error:", db_error)

        # ---------------- SOCKET SEND ----------------
        send_payload = {
            "rainfall": rainfall,
            "humidity": humidity,
            "pressure": pressure,
            "temperature": temperature,
            "relay1": int(data.get("relay1", 0)),
            "relay2": int(data.get("relay2", 0)),
            "relay3": int(data.get("relay3", 0)),
            "stage": stage_num,
            "stage_name": stage_name,
            "alert_level": alert_level,
            "algorithm_name": "RandomForestClassifier",
            "device_source": device_source,
            "esp32_connected": (time.time() - last_esp32_seen_ts) <= ESP32_TIMEOUT_SECONDS
        }

        print("[INFO] Sending to UI:", send_payload)

        socketio.emit('update', send_payload)

        return jsonify({"status": "success"})

    except Exception as e:
        print("[ERROR] Runtime Error:", e)
        return jsonify({"status": "error", "message": str(e)})

# -------------------------------
# DEVICE STATUS
# -------------------------------
@app.route('/api/device/status')
def get_device_status():
    now = time.time()
    age_seconds = int(now - last_esp32_seen_ts) if last_esp32_seen_ts > 0 else None
    connected = (age_seconds is not None) and (age_seconds <= ESP32_TIMEOUT_SECONDS)
    return jsonify({
        "connected": connected,
        "last_seen_seconds": age_seconds,
        "timeout_seconds": ESP32_TIMEOUT_SECONDS
    })


# -------------------------------
# RELAY COMMANDS
# -------------------------------
@app.route('/api/device/commands', methods=['GET', 'POST'])
def relay_commands():
    global relay_command_state

    if request.method == 'GET':
        # ESP32 expects plain-text command format.
        return (
            f"r1={relay_command_state['r1']},"
            f"r2={relay_command_state['r2']},"
            f"r3={relay_command_state['r3']}"
        )

    payload = request.get_json(silent=True) or request.form.to_dict() or {}
    relay_command_state['r1'] = clamp_relay_value(payload.get('r1', relay_command_state['r1']))
    relay_command_state['r2'] = clamp_relay_value(payload.get('r2', relay_command_state['r2']))
    relay_command_state['r3'] = clamp_relay_value(payload.get('r3', relay_command_state['r3']))

    socketio.emit('relay_state', relay_command_state)
    return jsonify({"status": "ok", "relay": relay_command_state})


@app.route('/api/device/commands/state', methods=['GET'])
def relay_command_state_api():
    return jsonify(relay_command_state)


# -------------------------------
# EMERGENCY PING
# -------------------------------
@app.route('/api/emergency/ping', methods=['POST'])
def emergency_ping():
    try:
        with urlrequest.urlopen(EMERGENCY_PING_URL, timeout=5) as resp:
            status_code = resp.getcode()
            body = resp.read(200).decode('utf-8', errors='ignore')

        payload = {
            "status": "success",
            "ping_status_code": status_code,
            "response": body
        }
        socketio.emit('emergency_ping', payload)
        return jsonify(payload)
    except urlerror.URLError as e:
        payload = {
            "status": "error",
            "message": str(e)
        }
        socketio.emit('emergency_ping', payload)
        return jsonify(payload), 502

# -------------------------------
# GET READINGS
# -------------------------------
@app.route('/api/readings')
def get_readings():
    if HARDWARE_MODE:
        conn = safe_get_db()
        if conn is None:
            return jsonify([])

        cursor = conn.cursor()

        try:
            cursor.execute("SELECT * FROM sensor_readings ORDER BY timestamp DESC LIMIT 20")
            data = cursor.fetchall()
        except Exception as db_error:
            print("[ERROR] DB Read Error:", db_error)
            cursor.close()
            conn.close()
            return jsonify([])

        result = []
        for row in data:
            row_dict = dict(row)
            if row_dict.get('timestamp'):
                row_dict['timestamp'] = str(row_dict['timestamp'])
            result.append(row_dict)

        cursor.close()
        conn.close()
        return jsonify(result)

    else:
        return jsonify([])

# -------------------------------
# ALERTS
# -------------------------------
@app.route('/api/alerts')
def get_alerts():
    return jsonify([])

# -------------------------------
# STATS
# -------------------------------
@app.route('/api/stats')
def get_stats():
    if HARDWARE_MODE:
        conn = safe_get_db()
        if conn is None:
            return jsonify({
                "total_readings": 0,
                "total_alerts": 0,
                "max_rainfall": 0
            })

        cursor = conn.cursor()

        try:
            cursor.execute("SELECT COUNT(*) as total FROM sensor_readings")
            total = cursor.fetchone()['total']

            cursor.execute("SELECT COUNT(*) as alerts FROM alert_history")
            alerts = cursor.fetchone()['alerts']

            cursor.execute("SELECT MAX(rain_intensity) as max_rain FROM sensor_readings")
            max_rain = cursor.fetchone()['max_rain']
        except Exception as db_error:
            print("[ERROR] DB Stats Error:", db_error)
            cursor.close()
            conn.close()
            return jsonify({
                "total_readings": 0,
                "total_alerts": 0,
                "max_rainfall": 0
            })

        cursor.close()
        conn.close()

        return jsonify({
            "total_readings": total,
            "total_alerts": alerts,
            "max_rainfall": max_rain
        })

    else:
        return jsonify({
            "total_readings": 0,
            "total_alerts": 0,
            "max_rainfall": 0
        })

# -------------------------------
# MAIN
# -------------------------------
if __name__ == '__main__':
    init_db()
    print("[INFO] Server Started...")
    socketio.run(app, debug=True, host='0.0.0.0', port=5000, allow_unsafe_werkzeug=True)