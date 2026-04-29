/**
 * ============================================================
 * HỆ THỐNG BARRIER TỰ ĐỘNG - ESP32-CAM
 * Phiên bản: 3.2 (Tích hợp SmartParking Valkyrie Python Server)
 * ============================================================
 * 
 * LUỒNG HOẠT ĐỘNG:
 * 1. GUI quét QR → Python POST /register-student (cache session)
 * 2. IR Sensor phát hiện xe → ESP32 gửi GET /api/vehicle-detected?lane=X
 * 3. Python nhận webhook → Python gọi ESP32 /capture
 * 4. ESP32 chụp ảnh → Trả về JPEG cho Python
 * 5. Python OCR (Google Vision) + Fuzzy Match + An ninh
 * 6. Python gọi ESP32 /open → Servo quay 90°
 * 
 * ENDPOINTS ESP32:
 *   GET /capture  → Chụp ảnh, trả JPEG
 *   GET /open     → Mở cổng (servo 90°)
 *   GET /ir_in    → Trạng thái IR sensor cổng vào (JSON)
 *   GET /ir_out   → Trạng thái IR sensor cổng ra (JSON)
 *   GET /status   → Trạng thái hệ thống (JSON)
 *   GET /latest   → Xem ảnh mới nhất
 * ============================================================
 */

#include <WiFi.h>
#include <WebServer.h>
#include <HTTPClient.h>
#include <ESP32Servo.h>
#include "esp_camera.h"
#include "soc/soc.h"
#include "soc/rtc_cntl_reg.h"

#if __has_include(<esp_arduino_version.h>)
#include <esp_arduino_version.h>
#endif

// ============================================================
// CẤU HÌNH IR SENSOR LOGIC
// ============================================================
// true  = HIGH khi có vật cản (ir_raw=1 khi che)
// false = LOW khi có vật cản (ir_raw=0 khi che)
// → Test: curl http://<ESP32_IP>/ir_in khi che/không che để xác định
#define IR_ACTIVE_HIGH true

// ============================================================
// CẤU HÌNH MẠNG
// ============================================================
const char* ssid = "Nobuuu";
const char* password = "244466666";
const char* python_server_ip = "10.202.90.178";
const int python_server_port = 8000;

// ============================================================
// CẤU HÌNH LANE (IN hoặc OUT — chọn 1 khi nạp code)
// ============================================================
const char* LANE = "IN";

// ============================================================
// CẤU HÌNH CHÂN CẮM
// ============================================================
#define IR_SENSOR_PIN 13
#define SERVO_PIN 14

// ============================================================
// CAMERA PINOUT (ESP32-CAM AI-Thinker)
// ============================================================
#define PWDN_GPIO_NUM     32
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM      0
#define SIOD_GPIO_NUM     26
#define SIOC_GPIO_NUM     27
#define Y9_GPIO_NUM       35
#define Y8_GPIO_NUM       34
#define Y7_GPIO_NUM       39
#define Y6_GPIO_NUM       36
#define Y5_GPIO_NUM       21
#define Y4_GPIO_NUM       19
#define Y3_GPIO_NUM       18
#define Y2_GPIO_NUM        5
#define VSYNC_GPIO_NUM    25
#define HREF_GPIO_NUM     23
#define PCLK_GPIO_NUM     22

// ============================================================
// BIẾN TOÀN CỤC
// ============================================================
WebServer server(80);
Servo myServo;

bool irEventLatched = false;
unsigned long lowStableSince = 0;
const unsigned long LOW_STABLE_TIME = 2000; // LOW phải ổn định 2 giây mới cho phép trigger lại

bool isGateOpen = false;
unsigned long gateOpenedAt = 0;
const unsigned long GATE_OPEN_DURATION = 7000;  // Mở cổng 7 giây (SG90)

uint8_t* latestFrameBuf = nullptr;
size_t   latestFrameLen = 0;
uint32_t latestFrameSeq = 0;

// ============================================================
// HÀM HELPER: Đọc IR có xe không (dùng IR_ACTIVE_HIGH)
// ============================================================
bool isVehicleDetected() {
  int irState = digitalRead(IR_SENSOR_PIN);
  return IR_ACTIVE_HIGH ? (irState == HIGH) : (irState == LOW);
}


// ============================================================
// HÀM KHỞI TẠO CAMERA
// ============================================================
bool setupCamera() {
  camera_config_t config;
  config.ledc_channel  = LEDC_CHANNEL_0;
  config.ledc_timer    = LEDC_TIMER_0;
  config.pin_d0        = Y2_GPIO_NUM;
  config.pin_d1        = Y3_GPIO_NUM;
  config.pin_d2        = Y4_GPIO_NUM;
  config.pin_d3        = Y5_GPIO_NUM;
  config.pin_d4        = Y6_GPIO_NUM;
  config.pin_d5        = Y7_GPIO_NUM;
  config.pin_d6        = Y8_GPIO_NUM;
  config.pin_d7        = Y9_GPIO_NUM;
  config.pin_xclk      = XCLK_GPIO_NUM;
  config.pin_pclk      = PCLK_GPIO_NUM;
  config.pin_vsync     = VSYNC_GPIO_NUM;
  config.pin_href      = HREF_GPIO_NUM;

  #if defined(ESP_ARDUINO_VERSION_MAJOR) && (ESP_ARDUINO_VERSION_MAJOR >= 3)
    config.pin_sccb_sda  = SIOD_GPIO_NUM;
    config.pin_sccb_scl  = SIOC_GPIO_NUM;
  #else
    config.pin_sscb_sda  = SIOD_GPIO_NUM;
    config.pin_sscb_scl  = SIOC_GPIO_NUM;
  #endif

  config.pin_pwdn      = PWDN_GPIO_NUM;
  config.pin_reset     = RESET_GPIO_NUM;
  config.xclk_freq_hz  = 10000000;
  config.pixel_format  = PIXFORMAT_JPEG;
  config.frame_size    = FRAMESIZE_VGA;
  config.jpeg_quality  = 12;
  config.fb_count      = 1;

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("❌ Camera init lỗi: 0x%x\n", err);
    return false;
  }
  Serial.println("✅ Camera khởi động thành công!");
  return true;
}

// ============================================================
// ĐIỀU KHIỂN SERVO
// ============================================================
void openGate() {
  if (isGateOpen) return;
  Serial.println("🔓 MỞ CỔNG - Servo quay 90°");
  myServo.write(90);
  isGateOpen = true;
  gateOpenedAt = millis();
}

void closeGate() {
  if (!isGateOpen) return;
  Serial.println("🔒 ĐÓNG CỔNG - Servo về 0°");
  myServo.write(0);
  isGateOpen = false;
}

// ============================================================
// FRAME CACHE
// ============================================================
void clearLatestFrame() {
  if (latestFrameBuf != nullptr) {
    free(latestFrameBuf);
    latestFrameBuf = nullptr;
    latestFrameLen = 0;
  }
}

bool cacheLatestFrame(camera_fb_t* fb) {
  if (!fb || !fb->buf || fb->len == 0) return false;
  uint8_t* newBuf = (uint8_t*)ps_malloc(fb->len);
  if (!newBuf) return false;
  memcpy(newBuf, fb->buf, fb->len);
  clearLatestFrame();
  latestFrameBuf = newBuf;
  latestFrameLen = fb->len;
  latestFrameSeq++;
  return true;
}

// ============================================================
// ENDPOINT /capture — Python gọi để lấy ảnh JPEG
// ============================================================
void handleCapture() {
  Serial.println("\n📸 [API] Python yêu cầu chụp ảnh...");
  camera_fb_t* fb = esp_camera_fb_get();
  if (!fb) {
    server.send(500, "application/json", "{\"error\":\"Camera failed\"}");
    return;
  }
  cacheLatestFrame(fb);
  server.sendHeader("Content-Type", "image/jpeg");
  server.sendHeader("Content-Length", String(fb->len));
  server.sendHeader("X-Frame-Seq", String(latestFrameSeq));
  server.send_P(200, "image/jpeg", (const char*)fb->buf, fb->len);
  Serial.printf("✅ Gửi ảnh (%d bytes, seq=%d)\n", fb->len, latestFrameSeq);
  esp_camera_fb_return(fb);
}

// ============================================================
// ENDPOINT /open — Python gọi để mở cổng
// ============================================================
void handleOpen() {
  Serial.println("🔓 [API] Python yêu cầu mở cổng!");
  openGate();
  server.send(200, "application/json", "{\"status\":\"ok\",\"message\":\"Gate opened\"}");
}

// ============================================================
// ENDPOINT /ir_in — Python kiểm tra IR sensor cổng VÀO
// ============================================================
void handleIrIn() {
  bool detected = isVehicleDetected();
  int irRaw = digitalRead(IR_SENSOR_PIN);

  String json = "{\"detected\":" + String(detected ? "true" : "false") +
                ",\"ir_raw\":" + String(irRaw) +
                ",\"lane\":\"IN\"}";

  server.send(200, "application/json", json);
  Serial.printf("🔍 [API] IR IN → %s (raw=%d)\n", detected ? "CÓ XE" : "TRỐNG", irRaw);
}

// ============================================================
// ENDPOINT /ir_out — Python kiểm tra IR sensor cổng RA
// ============================================================
void handleIrOut() {
  bool detected = isVehicleDetected();
  int irRaw = digitalRead(IR_SENSOR_PIN);

  String json = "{\"detected\":" + String(detected ? "true" : "false") +
                ",\"ir_raw\":" + String(irRaw) +
                ",\"lane\":\"OUT\"}";

  server.send(200, "application/json", json);
  Serial.printf("🔍 [API] IR OUT → %s (raw=%d)\n", detected ? "CÓ XE" : "TRỐNG", irRaw);
}

// ============================================================
// ENDPOINT /status — Trạng thái hệ thống JSON
// ============================================================
void handleStatus() {
  bool detected = isVehicleDetected();
  String json = "{";
  json += "\"wifi_connected\":true,";
  json += "\"wifi_rssi\":" + String(WiFi.RSSI()) + ",";
  json += "\"gate_open\":" + String(isGateOpen ? "true" : "false") + ",";
  json += "\"ir_detected\":" + String(detected ? "true" : "false") + ",";
  json += "\"ir_active_high\":" + String(IR_ACTIVE_HIGH ? "true" : "false") + ",";
  json += "\"lane\":\"" + String(LANE) + "\",";
  json += "\"free_heap\":" + String(ESP.getFreeHeap()) + ",";
  json += "\"latest_frame_seq\":" + String(latestFrameSeq) + ",";
  json += "\"ip\":\"" + WiFi.localIP().toString() + "\"";
  json += "}";
  server.send(200, "application/json", json);
}

// ============================================================
// ENDPOINT /latest — Xem ảnh mới nhất
// ============================================================
void handleLatest() {
  if (latestFrameBuf == nullptr || latestFrameLen == 0) {
    server.send(404, "text/plain", "No frame available");
    return;
  }
  server.sendHeader("Content-Type", "image/jpeg");
  server.sendHeader("X-Frame-Seq", String(latestFrameSeq));
  server.send_P(200, "image/jpeg", (const char*)latestFrameBuf, latestFrameLen);
}

// ============================================================
// ENDPOINT / — Trang chủ
// ============================================================
void handleRoot() {
  String html = "<!DOCTYPE html><html><head><meta charset='UTF-8'>";
  html += "<title>ESP32 Barrier</title></head><body>";
  html += "<h1>🚗 ESP32 Parking Barrier v3.2</h1>";
  html += "<p>Lane: <b>" + String(LANE) + "</b></p>";
  html += "<p>Gate: " + String(isGateOpen ? "OPEN 🔓" : "CLOSED 🔒") + "</p>";
  html += "<p>IR: " + String(isVehicleDetected() ? "CÓ XE 🚗" : "TRỐNG ⬜") + "</p>";
  html += "<p>IP: " + WiFi.localIP().toString() + "</p>";
  html += "<hr><h2>API:</h2><ul>";
  html += "<li><code>GET /capture</code> → Chụp ảnh JPEG</li>";
  html += "<li><code>GET /open</code> → Mở cổng</li>";
  html += "<li><code>GET /ir_in</code> → Trạng thái IR vào</li>";
  html += "<li><code>GET /ir_out</code> → Trạng thái IR ra</li>";
  html += "<li><code>GET /status</code> → JSON status</li>";
  html += "<li><code>GET /latest</code> → Ảnh mới nhất</li>";
  html += "</ul></body></html>";
  server.send(200, "text/html", html);
}

// ============================================================
// SETUP
// ============================================================
void setup() {
  Serial.begin(115200);
  delay(1000);
  WRITE_PERI_REG(RTC_CNTL_BROWN_OUT_REG, 0);

  Serial.println("\n╔════════════════════════════════════════╗");
  Serial.println("║  ESP32 PARKING BARRIER v3.2 VALKYRIE  ║");
  Serial.println("╚════════════════════════════════════════╝\n");

  pinMode(IR_SENSOR_PIN, INPUT);
  Serial.printf("✅ IR Sensor → GPIO %d (Active %s)\n", IR_SENSOR_PIN, IR_ACTIVE_HIGH ? "HIGH" : "LOW");

  ESP32PWM::allocateTimer(1);
  myServo.setPeriodHertz(50);
  myServo.attach(SERVO_PIN, 500, 2400);
  myServo.write(0);
  Serial.printf("✅ Servo → GPIO %d\n", SERVO_PIN);

  Serial.println("\n📷 Đang khởi động camera...");
  if (!setupCamera()) {
    Serial.println("⛔ Camera FAIL!");
    while (true) delay(1000);
  }

  Serial.printf("📶 Kết nối WiFi: %s\n", ssid);
  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid, password);
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 40) {
    delay(500);
    Serial.print(".");
    attempts++;
  }
  Serial.println();

  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("✅ WiFi OK! IP: %s | RSSI: %d dBm\n",
                  WiFi.localIP().toString().c_str(), WiFi.RSSI());
    Serial.printf("🐍 Python Server: %s:%d\n", python_server_ip, python_server_port);
  } else {
    Serial.println("⚠️ WiFi FAIL");
  }

  server.on("/", handleRoot);
  server.on("/capture", handleCapture);
  server.on("/open", handleOpen);
  server.on("/ir_in", handleIrIn);
  server.on("/ir_out", handleIrOut);
  server.on("/status", handleStatus);
  server.on("/latest", handleLatest);
  server.begin();

  camera_fb_t* warmup = esp_camera_fb_get();
  if (warmup) {
    cacheLatestFrame(warmup);
    esp_camera_fb_return(warmup);
  }

  Serial.printf("\n🚀 SẴN SÀNG! Lane=%s | IR Active %s | Chờ xe...\n", LANE, IR_ACTIVE_HIGH ? "HIGH" : "LOW");
  Serial.printf("🔍 IR state lúc startup: %s\n", isVehicleDetected() ? "✅ CÓ XE" : "❌ TRỐNG");
}

// ============================================================
// LOOP
// ============================================================
void loop() {
  server.handleClient();

  if (isGateOpen && (millis() - gateOpenedAt >= GATE_OPEN_DURATION)) {
    closeGate();
  }

  bool vehicleDetected = isVehicleDetected();
  unsigned long now = millis();

  if (vehicleDetected) {
    lowStableSince = 0;

    if (!irEventLatched) {
      irEventLatched = true;
      Serial.println("\n🚗 === IR PHÁT HIỆN XE! ===");

      if (WiFi.status() == WL_CONNECTED) {
        HTTPClient http;
        String url = "http://" + String(python_server_ip) + ":" +
                     String(python_server_port) + "/api/vehicle-detected?lane=" + String(LANE);

        Serial.printf("📡 Webhook → %s\n", url.c_str());
        http.begin(url);
        http.setTimeout(5000);
        int httpCode = http.GET();

        if (httpCode > 0) {
          Serial.printf("✅ Webhook gửi thành công! HTTP %d\n", httpCode);
          String response = http.getString();
          Serial.printf("   Response: %s\n", response.c_str());
        } else {
          Serial.printf("❌ Webhook FAILED: %s\n", http.errorToString(httpCode).c_str());
        }
        http.end();
      } else {
        Serial.printf("❌ WiFi mất kết nối! WiFi status: %d\n", WiFi.status());
        Serial.println("🔄 Đang reconnect...");
        WiFi.reconnect();
      }
    }
  } else {
    if (irEventLatched) {
      if (lowStableSince == 0) {
        lowStableSince = now;
      } else if (now - lowStableSince >= LOW_STABLE_TIME) {
        irEventLatched = false;
        lowStableSince = 0;
        Serial.println("↩️ IR LOW ổn định 2s, sẵn sàng bắt cạnh HIGH tiếp theo");
      }
    }
  }

  delay(20);
}
