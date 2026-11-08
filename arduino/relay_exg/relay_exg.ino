// Relay EXG reader.
// Samples the two EXG pills at a fixed rate and prints "t_us,a0,a1".
// Wiring uses three electrodes:
//   A0 = left-of-left-eye electrode minus upper-right-eye electrode
//   A1 = left-of-left-eye electrode minus lower-right-eye electrode
// Signal processing reconstructs horizontal movement from their average and
// vertical movement from their difference.
// TODO: verify BioAmp EXG Pill output range + wiring against Upside Down Labs docs.
//       250000 baud (exact divisor of 16 MHz, 0% error): 26-byte worst-case lines x 500 Hz = 13 kB/s < 25 kB/s.
//       115200 tops out near 440 lines/s and the loop falls behind.

const unsigned long SAMPLE_RATE_HZ = 500;
const unsigned long PERIOD_US = 1000000UL / SAMPLE_RATE_HZ;

unsigned long nextSampleUs = 0;

void setup() {
  Serial.begin(250000);
  nextSampleUs = micros();
}

void loop() {
  unsigned long now = micros();
  if ((long)(now - nextSampleUs) < 0) return;
  nextSampleUs += PERIOD_US;

  int a0 = analogRead(A0);
  int a1 = analogRead(A1);

  Serial.print(now);
  Serial.print(',');
  Serial.print(a0);
  Serial.print(',');
  Serial.println(a1);
}
