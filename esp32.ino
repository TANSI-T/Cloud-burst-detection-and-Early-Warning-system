#include <WiFi.h>
#include <HTTPClient.h>
#include "DHT.h"

// ===== WIFI =====
const char* ssid = "bm";
const char* password = "12345678";

// ===== SERVER =====
const char* serverBaseUrl = "http://10.250.233.148:5000";
const char* stage2Url = "http://10.250.233.181:8081/2";
const char* stage3Url = "http://10.250.233.181:8081/3";
String telemetryUrl = String(serverBaseUrl) + "/data";
String commandUrl = String(serverBaseUrl) + "/api/device/commands";

// ===== PINS =====
#define DHTPIN 4
#define DHTTYPE DHT22

#define RAIN_DO 26
#define SOIL_PIN 33
#define PRESSURE_PIN 34

#define RELAY_RAIN 14
#define RELAY_SOIL 27
#define RELAY_TEMP 25

#define BUTTON_PIN 32

DHT dht(DHTPIN, DHTTYPE);

// ===== SETTINGS =====
int soilThreshold = 2000;
float tempThreshold = 20.0;
float pressureThreshold = 1000.0;

// Pressure sensor conversion constants (tune for your module)
const float adcVref = 3.3;
const int adcMax = 4095;
const float pressureMinHpa = 900.0;
const float pressureMaxHpa = 1100.0;

// ===== TIMERS =====
unsigned long lastSampleMs = 0;
unsigned long lastPingMs = 0;
unsigned long lastTelemetryMs = 0;
unsigned long lastCommandMs = 0;

const unsigned long sampleIntervalMs = 2000;
const unsigned long pingIntervalMs = 10000;
const unsigned long telemetryIntervalMs = 3000;
const unsigned long commandIntervalMs = 3000;
const unsigned long buttonDebounceMs = 80;

// Desired states from local logic / dashboard.
int relayRainState = HIGH;
int relaySoilState = HIGH;
int relayTempState = HIGH;
int dashboardRelay1 = 0;

// Latest valid readings to handle transient sensor failures.
float lastValidTemp = 25.0;
float lastValidHumidity = 60.0;
float lastValidPressure = 1013.0;

bool isButtonPressedStable() {
  // INPUT_PULLUP: pressed = LOW
  if (digitalRead(BUTTON_PIN) != LOW) {
    return false;
  }
  delay(buttonDebounceMs);
  return digitalRead(BUTTON_PIN) == LOW;
}

void connectWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid, password);
  Serial.print("Connecting WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nConnected!");
  Serial.print("IP: ");
  Serial.println(WiFi.localIP());
}

float readPressureHpa() {
  long total = 0;
  const int samples = 10;

  for (int i = 0; i < samples; i++) {
    total += analogRead(PRESSURE_PIN);
    delay(2);
  }

  float avgAdc = total / (float)samples;
  float voltage = (avgAdc / adcMax) * adcVref;
  float pressure = pressureMinHpa + (voltage / adcVref) * (pressureMaxHpa - pressureMinHpa);
  return pressure;
}

float rainDigitalToIntensity(int rainDo) {
  // For digital rain module output: LOW means rain detected.
  return (rainDo == LOW) ? 120.0 : 0.0;
}

void triggerSmsEndpoint(const char* url, const char* stageLabel) {
  if (WiFi.status() != WL_CONNECTED) {
    return;
  }

  HTTPClient http;
  http.setConnectTimeout(3000);
  http.setTimeout(5000);
  Serial.print("Calling SMS URL for ");
  Serial.print(stageLabel);
  Serial.print(": ");
  Serial.println(url);

  http.begin(url);
  int code = http.GET();
  Serial.print("HTTP response code: ");
  Serial.println(code);
  if (code == 200) {
    Serial.print("SMS SENT for ");
    Serial.println(stageLabel);
  }
  http.end();
}

void sendTelemetry(float rain, int soil, float humidity, float temp, float pressure) {
  if (WiFi.status() != WL_CONNECTED) {
    return;
  }

  HTTPClient http;
  http.setConnectTimeout(3000);
  http.setTimeout(5000);
  String payload = "{";
  payload += "\"rain\":" + String(rain, 2) + ",";
  payload += "\"soil\":" + String(soil) + ",";
  payload += "\"humidity\":" + String(humidity, 2) + ",";
  payload += "\"pressure\":" + String(pressure, 2) + ",";
  payload += "\"temperature\":" + String(temp, 2) + ",";
  payload += "\"relay1\":" + String(relayRainState == LOW ? 1 : 0) + ",";
  payload += "\"relay2\":" + String(relaySoilState == LOW ? 1 : 0) + ",";
  payload += "\"relay3\":" + String(relayTempState == LOW ? 1 : 0);
  payload += "}";

  http.begin(telemetryUrl.c_str());
  http.addHeader("Content-Type", "application/json");
  int code = http.POST(payload);

  Serial.print("Telemetry code: ");
  Serial.println(code);
  if (code > 0) {
    Serial.println(http.getString());
  } else {
    Serial.print("Telemetry error: ");
    Serial.println(http.errorToString(code));
  }
  http.end();
}

void applyRelayOutput() {
  // ACTIVE LOW relays: LOW means ON.
  digitalWrite(RELAY_RAIN, relayRainState);
  digitalWrite(RELAY_SOIL, relaySoilState);
  digitalWrite(RELAY_TEMP, relayTempState);
}

void parseAndApplyCommand(String line) {
  // Expected format: r1=0,r2=1,r3=0
  line.replace(" ", "");
  int idxR1 = line.indexOf("r1=");
  int idxR2 = line.indexOf("r2=");
  int idxR3 = line.indexOf("r3=");

  if (idxR1 >= 0 && idxR2 >= 0 && idxR3 >= 0) {
    int v1 = line.substring(idxR1 + 3, idxR1 + 4).toInt();
    int v2 = line.substring(idxR2 + 3, idxR2 + 4).toInt();
    int v3 = line.substring(idxR3 + 3, idxR3 + 4).toInt();

    dashboardRelay1 = (v1 == 1) ? 1 : 0;
    relayRainState = (v1 == 1) ? LOW : HIGH;
    relaySoilState = (v2 == 1) ? LOW : HIGH;
    relayTempState = (v3 == 1) ? LOW : HIGH;
  }
}

void fetchCommandsFromDashboard() {
  if (WiFi.status() != WL_CONNECTED) {
    return;
  }

  HTTPClient http;
  http.setConnectTimeout(3000);
  http.setTimeout(5000);
  http.begin(commandUrl.c_str());
  int code = http.GET();

  if (code > 0) {
    String body = http.getString();
    Serial.print("Command code: ");
    Serial.println(code);
    Serial.print("Command body: ");
    Serial.println(body);
    parseAndApplyCommand(body);
  } else {
    Serial.print("Command fetch error: ");
    Serial.println(http.errorToString(code));
  }

  http.end();
}

void setup() {
  Serial.begin(115200);

  dht.begin();

  // INPUTS
  pinMode(RAIN_DO, INPUT_PULLUP);
  pinMode(SOIL_PIN, INPUT);
  pinMode(PRESSURE_PIN, INPUT);
  pinMode(BUTTON_PIN, INPUT_PULLUP);

  // OUTPUTS
  pinMode(RELAY_RAIN, OUTPUT);
  pinMode(RELAY_SOIL, OUTPUT);
  pinMode(RELAY_TEMP, OUTPUT);

  // RELAY OFF (ACTIVE LOW)
  digitalWrite(RELAY_RAIN, HIGH);
  digitalWrite(RELAY_SOIL, HIGH);
  digitalWrite(RELAY_TEMP, HIGH);

  connectWiFi();

  Serial.println("=== SERVER CONFIG ===");
  Serial.print("Telemetry URL: ");
  Serial.println(telemetryUrl);
  Serial.print("Command URL: ");
  Serial.println(commandUrl);
  Serial.print("Stage2 SMS URL: ");
  Serial.println(stage2Url);
  Serial.print("Stage3 SMS URL: ");
  Serial.println(stage3Url);
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    connectWiFi();
  }

  unsigned long now = millis();

  if (now - lastCommandMs >= commandIntervalMs) {
    fetchCommandsFromDashboard();
    lastCommandMs = now;
  }

  if (now - lastSampleMs >= sampleIntervalMs) {
    // ===== READ =====
    int rainDo = digitalRead(RAIN_DO);
    float rain = rainDigitalToIntensity(rainDo);
    int soil = analogRead(SOIL_PIN);

    float humidity = dht.readHumidity();
    float temp = dht.readTemperature();
    float pressure = readPressureHpa();

    if (!isnan(humidity)) {
      lastValidHumidity = humidity;
    } else {
      humidity = lastValidHumidity;
      Serial.println("Warning: DHT humidity read failed (NaN), using last valid value");
    }

    if (!isnan(temp)) {
      lastValidTemp = temp;
    } else {
      temp = lastValidTemp;
      Serial.println("Warning: DHT temp read failed (NaN), using last valid value");
    }

    if (!isnan(pressure) && pressure > 800.0 && pressure < 1200.0) {
      lastValidPressure = pressure;
    } else {
      pressure = lastValidPressure;
      Serial.println("Warning: pressure read out of range, using last valid value");
    }

    // ===== RAIN RELAY =====
    // Relay 1 turns ON if rain sensor detects rain OR dashboard requests r1=1.
    bool rainDetected = (rainDo == LOW);
    relayRainState = (rainDetected || dashboardRelay1 == 1) ? LOW : HIGH;

    // ===== SOIL RELAY =====
    relaySoilState = (soil < soilThreshold) ? LOW : HIGH;

    // ===== TEMP/PRESSURE RELAY =====
    // Stricter condition: require BOTH low temp and low pressure.
    // This prevents relay 3 from staying ON in normal conditions.
    const float effectivePressureThreshold = 980.0;
    relayTempState = (temp < tempThreshold && pressure < effectivePressureThreshold) ? LOW : HIGH;

    // ===== BUTTON =====
    // Pressing button forces ONLY relay 3 ON and keeps relay 2 OFF.
    if (isButtonPressedStable()) {
      relayTempState = LOW;
      relaySoilState = HIGH;
      Serial.println("BUTTON OVERRIDE: Relay3 forced ON, Relay2 forced OFF");
    }

    applyRelayOutput();

    // ===== DEBUG =====
    Serial.println("---- DATA ----");
    Serial.print("Rain_DO: "); Serial.println(rainDo);
    Serial.print("Rain Intensity: "); Serial.println(rain);
    Serial.print("Soil: "); Serial.println(soil);
    Serial.print("Humidity: "); Serial.println(humidity);
    Serial.print("Temp: "); Serial.println(temp);
    Serial.print("Pressure: "); Serial.println(pressure);
    Serial.print("Relay1 (Rain): "); Serial.println(relayRainState == LOW ? "ON" : "OFF");
    Serial.print("Relay1 source (rain/dashboard): ");
    Serial.print(rainDetected ? "RAIN " : "NO_RAIN ");
    Serial.println(dashboardRelay1 == 1 ? "+ DASHBOARD_ON" : "+ DASHBOARD_OFF");
    Serial.print("Relay2 (Soil): "); Serial.println(relaySoilState == LOW ? "ON" : "OFF");
    Serial.print("Relay3 (Temp/Pressure): "); Serial.println(relayTempState == LOW ? "ON" : "OFF");
    Serial.print("Ping condition (R2 or R3 ON): ");
    Serial.println((relaySoilState == LOW || relayTempState == LOW) ? "TRUE" : "FALSE");

    if (now - lastTelemetryMs >= telemetryIntervalMs) {
      sendTelemetry(rain, soil, humidity, temp, pressure);
      lastTelemetryMs = now;
    }

    if (now - lastPingMs >= pingIntervalMs) {
      // Trigger SMS URL for each active stage relay (ACTIVE LOW).
      if (relaySoilState == LOW) {
        triggerSmsEndpoint(stage2Url, "STAGE 2");
      }
      if (relayTempState == LOW) {
        triggerSmsEndpoint(stage3Url, "STAGE 3");
      }
      if (relaySoilState != LOW && relayTempState != LOW) {
        Serial.println("SMS skipped: relay2 and relay3 are both OFF");
      }
      lastPingMs = now;
    }

    lastSampleMs = now;
  }
}
