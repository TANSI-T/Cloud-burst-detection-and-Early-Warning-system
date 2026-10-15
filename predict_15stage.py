import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split

# Load & Train
df = pd.read_csv("cloudburst_15stage_dataset.csv")
X = df[["rainfall", "humidity", "pressure", "temperature"]]
y = df["label_num"]

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
model = RandomForestClassifier(n_estimators=100, random_state=42)
model.fit(X_train, y_train)

label_map = {
    0:  "☀️  Clear Weather",
    1:  "🌤  Cloud Formation",
    2:  "💧  High Humidity",
    3:  "🌦  Light Rain",
    4:  "🌧  Moderate Rain",
    5:  "🌧  Heavy Rain Start",
    6:  "🌧  Heavy Rain",
    7:  "🌨  Very Heavy Rain",
    8:  "⛈  Intense Rainfall",
    9:  "⛈  Extreme Rain",
    10: "🚨  Critical Rainfall",
    11: "🚨  Severe Rainfall",
    12: "🚨  Extreme Weather",
    13: "⚠️  Near Cloudburst",
    14: "🔴  CLOUDBURST STAGE!"
}

print("=" * 45)
print("  🌧 15 Stage Cloudburst Prediction System")
print("=" * 45)

rainfall    = float(input("Rainfall    (mm/hr) : "))
humidity    = float(input("Humidity    (%)     : "))
pressure    = float(input("Pressure    (hPa)   : "))
temperature = float(input("Temperature (°C)    : "))

input_data = pd.DataFrame([[rainfall, humidity, pressure, temperature]],
                           columns=["rainfall", "humidity", "pressure", "temperature"])

result = model.predict(input_data)[0]

print("\n" + "=" * 45)
print(f"  Stage {result} : {label_map[result]}")
print("=" * 45)
