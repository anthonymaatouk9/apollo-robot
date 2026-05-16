// ═══════════════════════════════════════════════════════
// APOLLO — Arduino Mega Main Sketch
// Handles all hardware: stepper, servo, IR, pump, ultrasonic
// Communicates with Raspberry Pi via Serial (115200 baud)
//
// COMMANDS RECEIVED FROM PI:
//   ROTATE_TUBE:n     — rotate stepper to tube n (1-4)
//   DISPENSE_PILL     — drop pill via servo
//   DISPENSE_CUP      — drop cup via servo
//   FILL_WATER:n      — fill n ml of water
//   RESET_TUBE        — go back to home position
//   PING              — respond with ACK:PING
//
// RESPONSES SENT TO PI:
//   ACK:COMMAND       — command acknowledged
//   PILL_CONFIRMED    — IR sensor confirmed pill drop
//   WATER_DONE        — water fill complete
//   CUP_OK            — cup dispensed
//   HOME_OK           — stepper at home
//   EVT:BATTERY:n     — battery level (sent every 10s)
//   ERR:REASON        — something went wrong
// ═══════════════════════════════════════════════════════

#include <Servo.h>
#include <AccelStepper.h>

// ── PIN DEFINITIONS ─────────────────────────────────────
// Stepper motor (tube selector) — using driver (STEP/DIR)
#define STEPPER_STEP_PIN  2
#define STEPPER_DIR_PIN   3
#define STEPPER_EN_PIN    4

// Pill servo
#define PILL_SERVO_PIN    5

// Cup servo
#define CUP_SERVO_PIN     6

// IR sensor (pill confirmation)
#define IR_PIN            7

// Water pump relay
#define PUMP_RELAY_PIN    8

// Ultrasonic sensor (cup detection)
#define TRIG_PIN          9
#define ECHO_PIN          10

// Battery voltage divider
#define BATTERY_PIN       A0

// ── CONSTANTS ───────────────────────────────────────────
#define STEPS_PER_TUBE    200   // stepper steps between tubes — CALIBRATE THIS
#define PILL_OPEN_ANGLE   90    // servo angle to drop pill
#define PILL_CLOSE_ANGLE  0     // servo angle closed
#define CUP_OPEN_ANGLE    90    // servo angle to drop cup
#define CUP_CLOSE_ANGLE   0     // servo angle closed
#define IR_TIMEOUT_MS     3000  // max ms to wait for IR confirmation
#define ML_PER_SECOND     50    // pump flow rate ml/s — CALIBRATE THIS
#define CUP_DETECT_CM     5     // ultrasonic distance to detect cup presence
#define BATTERY_INTERVAL  10000 // send battery reading every 10 seconds

// ── OBJECTS ─────────────────────────────────────────────
Servo pillServo;
Servo cupServo;
AccelStepper stepper(AccelStepper::DRIVER, STEPPER_STEP_PIN, STEPPER_DIR_PIN);

// ── STATE ────────────────────────────────────────────────
int  currentTube     = 1;
long lastBatteryTime = 0;
String inputBuffer   = "";

// ════════════════════════════════════════════════════════
void setup() {
  Serial.begin(115200);

  // Stepper
  pinMode(STEPPER_EN_PIN, OUTPUT);
  digitalWrite(STEPPER_EN_PIN, LOW); // enable driver
  stepper.setMaxSpeed(500);
  stepper.setAcceleration(200);

  // Servos
  pillServo.attach(PILL_SERVO_PIN);
  cupServo.attach(CUP_SERVO_PIN);
  pillServo.write(PILL_CLOSE_ANGLE);
  cupServo.write(CUP_CLOSE_ANGLE);

  // Sensors
  pinMode(IR_PIN,         INPUT);
  pinMode(TRIG_PIN,       OUTPUT);
  pinMode(ECHO_PIN,       INPUT);
  pinMode(PUMP_RELAY_PIN, OUTPUT);
  digitalWrite(PUMP_RELAY_PIN, LOW); // pump off

  Serial.println("ACK:BOOT");
}

// ════════════════════════════════════════════════════════
void loop() {
  // Read serial commands from Pi
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n') {
      inputBuffer.trim();
      if (inputBuffer.length() > 0) {
        handleCommand(inputBuffer);
      }
      inputBuffer = "";
    } else {
      inputBuffer += c;
    }
  }

  // Send battery reading periodically
  if (millis() - lastBatteryTime > BATTERY_INTERVAL) {
    sendBattery();
    lastBatteryTime = millis();
  }

  // Keep stepper running
  stepper.run();
}

// ════════════════════════════════════════════════════════
void handleCommand(String cmd) {
  // PING
  if (cmd == "PING") {
    Serial.println("ACK:PING");
    return;
  }

  // ROTATE_TUBE:n
  if (cmd.startsWith("ROTATE_TUBE:")) {
    int tube = cmd.substring(12).toInt();
    if (tube < 1 || tube > 4) {
      Serial.println("ERR:INVALID_TUBE");
      return;
    }
    rotateTube(tube);
    return;
  }

  // DISPENSE_PILL
  if (cmd == "DISPENSE_PILL") {
    dispensePill();
    return;
  }

  // DISPENSE_CUP
  if (cmd == "DISPENSE_CUP") {
    dispenseCup();
    return;
  }

  // FILL_WATER:n
  if (cmd.startsWith("FILL_WATER:")) {
    int ml = cmd.substring(11).toInt();
    fillWater(ml);
    return;
  }

  // RESET_TUBE
  if (cmd == "RESET_TUBE") {
    rotateTube(1);
    Serial.println("HOME_OK");
    return;
  }

  Serial.println("ERR:UNKNOWN_COMMAND");
}

// ════════════════════════════════════════════════════════
void rotateTube(int targetTube) {
  Serial.println("ACK:ROTATE_TUBE");
  long stepsNeeded = (long)(targetTube - currentTube) * STEPS_PER_TUBE;
  stepper.move(stepsNeeded);
  while (stepper.distanceToGo() != 0) {
    stepper.run();
  }
  currentTube = targetTube;
  Serial.print("ACK:TUBE_");
  Serial.println(targetTube);
}

// ════════════════════════════════════════════════════════
void dispensePill() {
  Serial.println("ACK:DISPENSE_PILL");

  // Open servo to drop pill
  pillServo.write(PILL_OPEN_ANGLE);
  delay(500);
  pillServo.write(PILL_CLOSE_ANGLE);

  // Wait for IR sensor to confirm pill passed
  unsigned long start = millis();
  bool confirmed = false;
  while (millis() - start < IR_TIMEOUT_MS) {
    if (digitalRead(IR_PIN) == LOW) { // LOW = object detected
      confirmed = true;
      break;
    }
    delay(10);
  }

  if (confirmed) {
    Serial.println("PILL_CONFIRMED");
  } else {
    Serial.println("ERR:NO_PILL_DETECTED");
  }
}

// ════════════════════════════════════════════════════════
void dispenseCup() {
  Serial.println("ACK:DISPENSE_CUP");
  cupServo.write(CUP_OPEN_ANGLE);
  delay(600);
  cupServo.write(CUP_CLOSE_ANGLE);
  delay(300);

  // Confirm cup presence with ultrasonic
  float dist = getUltrasonicCM();
  if (dist < CUP_DETECT_CM) {
    Serial.println("CUP_OK");
  } else {
    Serial.println("ERR:NO_CUP_DETECTED");
  }
}

// ════════════════════════════════════════════════════════
void fillWater(int ml) {
  // Check cup is present first
  float dist = getUltrasonicCM();
  if (dist > CUP_DETECT_CM) {
    Serial.println("ERR:NO_CUP_FOR_WATER");
    return;
  }

  Serial.println("ACK:FILL_WATER");

  // Run pump for calculated duration
  int pumpDuration = (ml * 1000) / ML_PER_SECOND;
  digitalWrite(PUMP_RELAY_PIN, HIGH);
  delay(pumpDuration);
  digitalWrite(PUMP_RELAY_PIN, LOW);

  Serial.println("WATER_DONE");
}

// ════════════════════════════════════════════════════════
float getUltrasonicCM() {
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);
  long duration = pulseIn(ECHO_PIN, HIGH, 30000);
  return duration * 0.034 / 2.0;
}

// ════════════════════════════════════════════════════════
void sendBattery() {
  int raw = analogRead(BATTERY_PIN);
  // Convert ADC reading to percentage
  // Assuming voltage divider: 12V max → 5V ADC
  // 12V = 1023, 0V = 0 → scale to 0-100%
  int pct = map(raw, 0, 1023, 0, 100);
  pct = constrain(pct, 0, 100);
  Serial.print("EVT:BATTERY:");
  Serial.println(pct);
}
