// Relay EXG reader. Owner: Role B.
// Samples A0-A2 at a fixed rate and prints "t_us,a0,a1,a2" at 250000 baud.
// Channel map: A0 = horizontal EOG, A1 = vertical EOG/blinks, A2 = unused.
// Boards: Arduino Uno (5 V) or Nano 33 BLE (3.3 V logic, analog pins NOT 5 V tolerant: power the pills from 3.3 V).
// TODO: verify BioAmp EXG Pill output range + wiring against Upside Down Labs docs.
//       250000 baud (exact divisor of 16 MHz, 0% error): 26-byte worst-case lines x 500 Hz = 13 kB/s < 25 kB/s.
//       115200 tops out near 440 lines/s and the loop falls behind.

const unsigned long SAMPLE_RATE_HZ = 500;
const unsigned long PERIOD_US = 1000000UL / SAMPLE_RATE_HZ;

unsigned long nextSampleUs = 0;

void setup() {
  Serial.begin(250000);  // native USB on the Nano 33 BLE ignores the rate; the Uno needs it
#ifdef ARDUINO_ARCH_MBED
  analogReadResolution(10);  // 10-bit like the Uno, so counts stay comparable (AVR is always 10-bit)
#endif
  nextSampleUs = micros();
}

void loop() {
  unsigned long now = micros();
  if ((long)(now - nextSampleUs) < 0) return;
  nextSampleUs += PERIOD_US;

  int a0 = analogRead(A0);
  int a1 = analogRead(A1);
  int a2 = analogRead(A2);

  Serial.print(now);
  Serial.print(',');
  Serial.print(a0);
  Serial.print(',');
  Serial.print(a1);
  Serial.print(',');
  Serial.println(a2);
}
