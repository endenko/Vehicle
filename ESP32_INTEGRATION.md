# ESP32-CAM Integration Guide 🎥

## 📋 Tổng quan

ESP32-CAM module sẽ:
1. Dùng cảm biến IR phát hiện xe
2. Chụp ảnh biển số khi xe vào/ra
3. POST ảnh đến FastAPI server trên laptop
4. Nhận lệnh mở barrier từ server

---

## 🔌 Hardware Setup

### Thành phần cần thiết:
- **ESP32-CAM module** (OV2640 camera)
- **IR Sensor module** (HC-SR501 hoặc tương đương)
- **Servo motor** (cho barrier)
- **USB-TTL adapter** (để nạp code)
- **Power supply** (5V 2A)

### Sơ đồ kết nối:

```
ESP32-CAM              IR Sensor            Servo Motor
--------               ---------            -----------
GND ────────────────── GND                  GND
5V  ────────────────── VCC                  VCC (5V)
GPIO 12 ──────────────  OUT                 (PWM control)
```

---

## 💻 Code ESP32

### Arduino Sketch Template

```cpp
#include <WiFi.h>
#include <HTTPClient.h>
#include <esp32-camera.h>
#include <ESP32Servo.h>

// WiFi
const char* SSID = "Your_WiFi_SSID";
const char* PASSWORD = "Your_WiFi_Password";

// API Server
const char* API_URL = "http://192.168.x.x:8000/process-plate";
const char* REGISTER_URL = "http://192.168.x.x:8000/register-student";

// Pins
const int IR_SENSOR_PIN = 12;
const int SERVO_PIN = 13;

// Camera
camera_config_t config;

// Global variables
Servo barrierServo;
volatile bool ir_triggered = false;
String current_student_id = "";

// ==================================================
// Setup
// ==================================================
void setup() {
  Serial.begin(115200);
  delay(1000);
  
  Serial.println("\n\n[ESP32-CAM] SmartParking Valkyrie Init");
  
  // WiFi
  setupWiFi();
  
  // Camera
  setupCamera();
  
  // IR Sensor
  pinMode(IR_SENSOR_PIN, INPUT);
  attachInterrupt(digitalPinToInterrupt(IR_SENSOR_PIN), onIRTrigger, RISING);
  
  // Servo
  barrierServo.attach(SERVO_PIN);
  closeBarrier();
  
  Serial.println("[✓] ESP32-CAM sẵn sàng!");
}

// ==================================================
// WiFi Setup
// ==================================================
void setupWiFi() {
  Serial.print("[WiFi] Kết nối đến ");
  Serial.println(SSID);
  
  WiFi.mode(WIFI_STA);
  WiFi.begin(SSID, PASSWORD);
  
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 20) {
    delay(500);
    Serial.print(".");
    attempts++;
  }
  
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("");
    Serial.println("[✓] WiFi kết nối!");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("[✗] Không thể kết nối WiFi");
  }
}

// ==================================================
// Camera Setup
// ==================================================
void setupCamera() {
  // OV2640 (default ESP32-CAM)
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_freq_hz = 20000000;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  // ... (đầy đủ pin config)
  config.pin_href = HREF_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.frame_size = FRAMESIZE_UXGA;
  config.pixel_format = PIXFORMAT_JPEG;
  config.grab_mode = CAMERA_GRAB_LATEST;
  config.fb_location = CAMERA_FB_IN_PSRAM;
  config.jpeg_quality = 12;
  config.fb_count = 1;
  
  // Init camera
  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.print("[✗] Camera init lỗi: ");
    Serial.println(err);
    return;
  }
  
  Serial.println("[✓] Camera khởi tạo thành công");
}

// ==================================================
// IR Sensor Interrupt
// ==================================================
void IRAM_ATTR onIRTrigger() {
  ir_triggered = true;
}

// ==================================================
// Main Loop
// ==================================================
void loop() {
  // Nếu IR trigger
  if (ir_triggered) {
    ir_triggered = false;
    
    Serial.println("[→] IR triggered! Chụp ảnh...");
    delay(200); // Anti-bounce
    
    // Chụp ảnh
    camera_fb_t* fb = esp_camera_fb_get();
    if (!fb) {
      Serial.println("[✗] Lỗi chụp ảnh");
      return;
    }
    
    // POST ảnh đến API
    sendToAPI(fb->buf, fb->len);
    
    esp_camera_fb_return(fb);
  }
  
  delay(100);
}

// ==================================================
// Send to API
// ==================================================
void sendToAPI(uint8_t* image_data, size_t image_size) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[✗] WiFi không kết nối");
    return;
  }
  
  HTTPClient http;
  
  Serial.println("[→] Gửi ảnh đến API...");
  
  http.begin(API_URL);
  http.addHeader("Content-Type", "application/octet-stream");
  
  // Thêm ma_sv nếu có
  String url_with_params = String(API_URL);
  if (current_student_id != "") {
    url_with_params += "?ma_sv=" + current_student_id;
  }
  
  http.begin(url_with_params);
  int httpCode = http.POST(image_data, image_size);
  
  if (httpCode == 200) {
    String response = http.getString();
    Serial.print("[✓] API response: ");
    Serial.println(response);
    
    // Parse JSON response để lấy status
    if (response.indexOf("\"status\": \"accepted\"") > 0) {
      openBarrier();  // Mở barrier
    } else {
      Serial.println("[✗] Xe bị từ chối");
    }
  } else {
    Serial.print("[✗] HTTP Error: ");
    Serial.println(httpCode);
  }
  
  http.end();
}

// ==================================================
// Barrier Control
// ==================================================
void openBarrier() {
  Serial.println("[→] Mở barrier...");
  for (int pos = 0; pos <= 90; pos++) {
    barrierServo.write(pos);
    delay(15);
  }
  // Giữ mở 3 giây
  delay(3000);
  closeBarrier();
}

void closeBarrier() {
  Serial.println("[→] Đóng barrier...");
  for (int pos = 90; pos >= 0; pos--) {
    barrierServo.write(pos);
    delay(15);
  }
}

// ==================================================
// Handle Server Events (Optional)
// ==================================================
// Có thể thêm web server để nhận lệnh từ server
// HTTPServer handler cho mở/đóng barrier từ xa
```

---

## 🔧 Cấu hình WiFi

1. Thay `SSID` + `PASSWORD` bằng WiFi của bạn
2. Thay `API_URL` bằng IP của laptop chạy server (ví dụ: `http://192.168.1.100:8000`)

---

## 📡 Data Flow

```
ESP32-CAM
   ↓
[IR Trigger]
   ↓
[Chụp ảnh]
   ↓
[POST ảnh → API]
   ↓
FastAPI Server
   ↓
[Google Vision OCR]
   ↓
[Fuzzy Matching]
   ↓
[Trả response: accepted/rejected]
   ↓
ESP32-CAM
   ↓
[Servo: Mở/Đóng barrier]
```

---

## 🧪 Testing

### Test WiFi:
```
Serial Monitor → Kiểm tra "WiFi kết nối!" message
```

### Test Camera:
```
Nhấn RESET → Kiểm tra "[✓] Camera khởi tạo thành công"
```

### Test IR Sensor:
```
Đặt tay qua IR sensor → Serial sẽ in "[→] IR triggered!"
```

### Test API:
```
Dùng curl từ laptop:
curl -X POST \
  -F "file=@test.jpg" \
  -F "ma_sv=SV21001" \
  http://127.0.0.1:8000/process-plate
```

---

## ⚠️ Troubleshooting

| Vấn đề | Giải pháp |
|--------|----------|
| Camera không khởi động | Check pin config, enable PSRAM |
| WiFi không kết nối | Kiểm tra SSID/Password, signal strength |
| IR không trigger | Check GPIO pin, pull-up resistor |
| Servo không chuyển động | Kiểm tra servo power, PWM pin |
| API 404 error | Kiểm tra IP server, port 8000 mở |

---

## 📚 Resources

- [ESP32-CAM pinout](https://github.com/espressif/esp32-camera)
- [Arduino IDE setup](https://docs.espressif.com/projects/arduino-esp32/en/latest/installing.html)
- [HTTPClient API](https://randomnerdtutorials.com/esp32-http-get-post-arduino/)

---

**Made with ❤️ by Sensei - April 2026**
