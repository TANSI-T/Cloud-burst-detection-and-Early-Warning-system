import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
import mysql.connector
import random
import time

# ✅ MySQL Connect
conn = mysql.connector.connect(
    host="localhost",
    user="root",
    password="root123",  
    database="cloudburst_project"
)
cursor = conn.cursor()
print("✅ DB Connected!")

# ✅ Load & Train Model
df = pd.read_csv("cloudburst_15stage_dataset.csv")
X = df[["rainfall", "humidity", "pressure", "temperature"]]
y = df["label_num"]
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
model = RandomForestClassifier(n_estimators=100, random_state=42)
model.fit(X_train, y_train)
print("✅ Model Trained!")

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

def save_reading(r, h, p, t, stage_num, stage_name, alert_level):
    query = """INSERT INTO sensor_readings 
               (sensor_id, rain_intensity, duration, cloudburst, local_alert, sms_sent)
               VALUES (%s, %s, %s, %s, %s, %s)"""
    cloudburst = 1 if stage_num >= 14 else 0
    local_alert = 1 if stage_num >= 9 else 0
    sms_sent = 1 if stage_num >= 12 else 0
    cursor.execute(query, ('SENSOR_01', r, t, cloudburst, local_alert, sms_sent))
    conn.commit()

def save_alert(stage_num, stage_name, r, h, p, t, message):
    query = """INSERT INTO alert_history
               (stage_num, stage_name, rainfall, humidity, pressure, temperature, alert_message)
               VALUES (%s, %s, %s, %s, %s, %s, %s)"""
    cursor.execute(query, (stage_num, stage_name, r, h, p, t, message))
    conn.commit()

# ✅ Simulate 20 readings and save
print("\n📡 Saving sensor readings to DB...\n")
for i in range(20):
    # Random sensor values
    r = round(random.uniform(0, 250), 2)
    h = round(random.uniform(20, 100), 2)
    p = round(random.uniform(960, 1030), 2)
    t = round(random.uniform(4, 40), 2)

    # Predict
    input_data = pd.DataFrame([[r, h, p, t]],
                               columns=["rainfall","humidity","pressure","temperature"])
    stage_num = int(model.predict(input_data)[0])
    stage_name = label_map[stage_num]
    alert_level = get_alert_level(stage_num)

    # Save to DB
    save_reading(r, h, p, t, stage_num, stage_name, alert_level)

    # Save alert if needed
    if stage_num >= 9:
        save_alert(stage_num, stage_name, r, h, p, t,
                   f"Stage {stage_num} detected! {stage_name} at Shimla Hill Slope.")

    print(f"Reading {i+1:02d} → Stage {stage_num} | {stage_name} | {alert_level}")
    time.sleep(0.5)

print("\n✅ All 20 readings saved to DB!")
print("Check MySQL Workbench → cloudburst_project → sensor_readings!")
cursor.close()
conn.close()