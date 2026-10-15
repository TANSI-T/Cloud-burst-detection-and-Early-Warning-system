import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.tree import DecisionTreeClassifier, plot_tree
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, classification_report
import matplotlib.pyplot as plt

# Load
df = pd.read_csv("cloudburst_15stage_dataset.csv")

X = df[["rainfall", "humidity", "pressure", "temperature"]]
y = df["label_num"]

label_names = [
    "Clear Weather", "Cloud Formation", "High Humidity",
    "Light Rain", "Moderate Rain", "Heavy Rain Start",
    "Heavy Rain", "Very Heavy Rain", "Intense Rainfall",
    "Extreme Rain", "Critical Rainfall", "Severe Rainfall",
    "Extreme Weather", "Near Cloudburst", "Cloudburst Stage"
]

# Split
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

# Train
dt = DecisionTreeClassifier(max_depth=10, random_state=42)
dt.fit(X_train, y_train)

rf = RandomForestClassifier(n_estimators=100, random_state=42)
rf.fit(X_train, y_train)

# Results
print("=" * 45)
print(f"🌳 Decision Tree : {accuracy_score(y_test, dt.predict(X_test))*100:.2f}%")
print(f"🌲 Random Forest : {accuracy_score(y_test, rf.predict(X_test))*100:.2f}%")
print("=" * 45)
print("\n📊 Random Forest Report:")
print(classification_report(y_test, rf.predict(X_test), target_names=label_names))

# Visualize
plt.figure(figsize=(25, 10))
plot_tree(dt, feature_names=X.columns, class_names=label_names, filled=True, fontsize=7)
plt.title("15 Stage Cloudburst Detection Tree")
plt.tight_layout()
plt.savefig("decision_tree_15stage.png")
print("🌳 Tree saved as decision_tree_15stage.png")
plt.show()