// Relay EXG reader. Owner: Role B.
// Samples A0-A2 at a fixed rate and prints "t_us,a0,a1,a2" at 115200 baud.
// Channel map: A0 = horizontal EOG, A1 = vertical EOG/blinks, A2 = jaw EMG.
// TODO: verify BioAmp EXG Pill output range + wiring against Upside Down Labs docs.
//       At 115200 baud, ~25 bytes/line caps us near 460 lines/s; raise baud (230400) if needed.

const unsigned long SAMPLE_RATE_HZ = 500;
const unsigned long PERIOD_US = 1000000UL / SAMPLE_RATE_HZ;

unsigned long nextSampleUs = 0;

void setup() {
  Serial.begin(115200);
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
