// toyota-tap-logger, 22R-E firmware: passive signal logger for a Toyota 22R-E engine.
//
// READ ONLY. No pin that connects to the car is ever set as an output.
// The only outputs are the bench simulator pins D9-D11, and they stay
// high-impedance (INPUT) unless a SIM command turns the simulator on.
//
// Serial: 115200 8N1. Commands (one per line):
//   ID            print firmware id
//   PROBE         1 second of min/max/avg on every analog pin + edge counts
//   GO            start streaming data frames (prints an H header line first)
//   STOP          stop streaming
//   RATE <hz>     frame rate, 1-100 (default 50)
//   SIM <rpm>     bench only: drive fake crank/IGT/injector on D9/D10/D11
//   SIM 0         simulator off, pins back to high-impedance
//
// Frame line (all integers):
//   D,ms,a0..a7,crank_us,igt_us,dwell_us,rise_ac_us,fall_ac_us,spark_crank_us,inj_us,inj_n
//   a0..a7          average raw ADC counts (0-1023) over the frame
//   crank_us        last crank period (one pulse per crank rev), 0 if stalled
//   igt_us          last IGT rise-to-rise period (2 per rev on a 4-cyl), 0 if stalled
//   dwell_us        last IGT high time
//   rise_ac_us      time from the last crank pulse to the last IGT rising edge
//   fall_ac_us      time from the last crank pulse to the last IGT falling edge
//   spark_crank_us  crank period at the moment of that falling edge
//   inj_us          average injector on-time over the frame, inj_n pulses

#include <Arduino.h>

#define FW_ID "TAP-LOGGER 22RE 0.2"

// ---- car inputs ----
const uint8_t PIN_CRANK = 2;  // INT0  crank pickup (hall, active low)
const uint8_t PIN_IGT = 3;    // INT1  ECU IGT output through 10k
const uint8_t PIN_INJ = 4;    // PCINT20  injector low side through divider (low = injecting)

// ---- bench simulator outputs (PORTB). Never wire these to the car. ----
const uint8_t SIM_CRANK = 9;   // PB1
const uint8_t SIM_IGT = 10;    // PB2
const uint8_t SIM_INJ = 11;    // PB3

const uint8_t N_AN = 8;
const uint8_t AN_PINS[N_AN] = {A0, A1, A2, A3, A4, A5, A6, A7};

// ---- edge capture state (written in ISRs) ----
volatile uint32_t crankLast = 0, crankPeriod = 0;
volatile uint16_t crankEdges = 0;

volatile bool igtHigh = false;
volatile uint32_t igtRise = 0, igtLastEdge = 0, igtPeriod = 0, igtDwell = 0;
volatile uint32_t riseAfterCrank = 0, fallAfterCrank = 0, sparkCrankPeriod = 0;
volatile uint16_t igtEdges = 0;

volatile bool injOn = false;
volatile uint32_t injStart = 0, injEnd = 0, injPwSum = 0, injLastEdge = 0;
volatile uint16_t injN = 0, injEdges = 0;

void isrCrank() {
  uint32_t now = micros();
  if (crankLast && now - crankLast < 3000UL) return;  // faster than 20,000 rpm = noise
  if (crankLast) crankPeriod = now - crankLast;
  crankLast = now;
  crankEdges++;
}

void isrIgt() {
  uint32_t now = micros();
  bool level = PIND & (1 << 3);
  igtEdges++;
  if (level && !igtHigh) {
    igtHigh = true;
    if (igtRise) igtPeriod = now - igtRise;
    igtRise = now;
    igtLastEdge = now;
    if (crankLast) riseAfterCrank = now - crankLast;
  } else if (!level && igtHigh) {
    if (now - igtRise < 200UL) return;  // glitch
    igtHigh = false;
    igtDwell = now - igtRise;
    igtLastEdge = now;
    if (crankLast) {
      fallAfterCrank = now - crankLast;
      sparkCrankPeriod = crankPeriod;
    }
  }
}

ISR(PCINT2_vect) {
  uint32_t now = micros();
  bool level = PIND & (1 << 4);
  if (!level && !injOn) {
    if (injEnd && now - injEnd < 500UL) return;  // flyback ringing after close
    injOn = true;
    injStart = now;
    injLastEdge = now;
    injEdges++;
  } else if (level && injOn) {
    if (now - injStart < 200UL) return;
    injOn = false;
    injEnd = now;
    injLastEdge = now;
    injPwSum += now - injStart;
    injN++;
    injEdges++;
  }
}

// ---- bench simulator: Timer2 at 20 kHz (50 us ticks) ----
volatile uint32_t simPeriod = 0, simPhase = 0, simS1 = 0, simS2 = 0, simInj = 0;
const uint32_t SIM_TICK = 50, SIM_DWELL = 3000, SIM_INJ_PW = 2500, SIM_CRANK_W = 1000;

ISR(TIMER2_COMPA_vect) {
  uint32_t p = simPhase + SIM_TICK;
  if (p >= simPeriod) p -= simPeriod;
  simPhase = p;
  uint8_t out = PORTB & ~((1 << 1) | (1 << 2) | (1 << 3));
  if (p >= SIM_CRANK_W) out |= (1 << 1);  // crank: active low pulse at 0 deg
  if ((p + SIM_DWELL >= simS1 && p < simS1) || (p + SIM_DWELL >= simS2 && p < simS2))
    out |= (1 << 2);  // IGT high during dwell, falls at 170 and 350 deg
  if (!(p >= simInj && p < simInj + SIM_INJ_PW)) out |= (1 << 3);  // injector low = on
  PORTB = out;
}

void simStop() {
  TIMSK2 = 0;
  simPeriod = 0;
  pinMode(SIM_CRANK, INPUT);
  pinMode(SIM_IGT, INPUT);
  pinMode(SIM_INJ, INPUT);
}

void simStart(uint32_t rpm) {
  simStop();
  if (rpm < 300 || rpm > 6000) return;
  uint32_t period = 60000000UL / rpm;
  noInterrupts();
  simPeriod = period;
  simPhase = 0;
  simS1 = period / 36UL * 17UL;   // 170 deg
  simS2 = period / 36UL * 35UL;   // 350 deg
  simInj = period / 4UL;          // 90 deg
  interrupts();
  digitalWrite(SIM_CRANK, HIGH);
  digitalWrite(SIM_INJ, HIGH);
  digitalWrite(SIM_IGT, LOW);
  pinMode(SIM_CRANK, OUTPUT);
  pinMode(SIM_IGT, OUTPUT);
  pinMode(SIM_INJ, OUTPUT);
  TCCR2A = (1 << WGM21);  // CTC
  TCCR2B = (1 << CS21);   // /8 -> 2 MHz
  OCR2A = 99;             // 20 kHz
  TCNT2 = 0;
  TIMSK2 = (1 << OCIE2A);
}

// ---- main ----
bool streaming = false;
uint16_t frameMs = 20;
uint32_t frameStart = 0;
uint32_t anSum[N_AN];
uint16_t anCnt[N_AN];
uint8_t anNext = 0;
char cmd[24];
uint8_t cmdLen = 0;

void resetFrame() {
  for (uint8_t i = 0; i < N_AN; i++) { anSum[i] = 0; anCnt[i] = 0; }
}

void sampleOne() {
  anSum[anNext] += analogRead(AN_PINS[anNext]);
  anCnt[anNext]++;
  anNext = (anNext + 1) % N_AN;
}

void printHeader() {
  Serial.println(F("H,ms,a0,a1,a2,a3,a4,a5,a6,a7,crank_us,igt_us,dwell_us,rise_ac_us,fall_ac_us,spark_crank_us,inj_us,inj_n"));
}

void emitFrame(uint32_t nowMs) {
  uint32_t now = micros();
  noInterrupts();
  uint32_t cP = crankPeriod, cL = crankLast;
  uint32_t iP = igtPeriod, iL = igtLastEdge, dw = igtDwell;
  uint32_t rac = riseAfterCrank, fac = fallAfterCrank, scp = sparkCrankPeriod;
  uint32_t pw = injPwSum;
  uint16_t n = injN;
  injPwSum = 0;
  injN = 0;
  interrupts();
  if (!cL || now - cL > 1000000UL) { cP = 0; }
  if (!iL || now - iL > 1000000UL) { iP = 0; dw = 0; rac = 0; fac = 0; scp = 0; }
  Serial.print('D'); Serial.print(','); Serial.print(nowMs);
  for (uint8_t i = 0; i < N_AN; i++) {
    Serial.print(',');
    Serial.print(anCnt[i] ? (anSum[i] + anCnt[i] / 2) / anCnt[i] : 0);
  }
  Serial.print(','); Serial.print(cP);
  Serial.print(','); Serial.print(iP);
  Serial.print(','); Serial.print(dw);
  Serial.print(','); Serial.print(rac);
  Serial.print(','); Serial.print(fac);
  Serial.print(','); Serial.print(scp);
  Serial.print(','); Serial.print(n ? pw / n : 0);
  Serial.print(','); Serial.println(n);
}

void doProbe() {
  uint16_t mn[N_AN], mx[N_AN];
  uint32_t sum[N_AN];
  uint16_t cnt[N_AN];
  for (uint8_t i = 0; i < N_AN; i++) { mn[i] = 1023; mx[i] = 0; sum[i] = 0; cnt[i] = 0; }
  noInterrupts();
  uint16_t c0 = crankEdges, g0 = igtEdges, j0 = injEdges;
  interrupts();
  uint32_t t0 = millis();
  uint8_t ch = 0;
  while (millis() - t0 < 1000) {
    uint16_t v = analogRead(AN_PINS[ch]);
    if (v < mn[ch]) mn[ch] = v;
    if (v > mx[ch]) mx[ch] = v;
    sum[ch] += v;
    cnt[ch]++;
    ch = (ch + 1) % N_AN;
  }
  noInterrupts();
  uint16_t c1 = crankEdges, g1 = igtEdges, j1 = injEdges;
  interrupts();
  for (uint8_t i = 0; i < N_AN; i++) {
    Serial.print(F("P,A")); Serial.print(i);
    Serial.print(','); Serial.print(mn[i]);
    Serial.print(','); Serial.print(mx[i]);
    Serial.print(','); Serial.println(cnt[i] ? sum[i] / cnt[i] : 0);
  }
  Serial.print(F("P,D2,")); Serial.print((uint16_t)(c1 - c0)); Serial.print(','); Serial.println(digitalRead(PIN_CRANK));
  Serial.print(F("P,D3,")); Serial.print((uint16_t)(g1 - g0)); Serial.print(','); Serial.println(digitalRead(PIN_IGT));
  Serial.print(F("P,D4,")); Serial.print((uint16_t)(j1 - j0)); Serial.print(','); Serial.println(digitalRead(PIN_INJ));
  Serial.println(F("P,END"));
}

void handleCommand(char *c) {
  if (!strcmp(c, "ID")) {
    Serial.println(F(FW_ID));
  } else if (!strcmp(c, "PROBE")) {
    bool was = streaming;
    streaming = false;
    doProbe();
    streaming = was;
  } else if (!strcmp(c, "GO")) {
    printHeader();
    resetFrame();
    frameStart = millis();
    streaming = true;
  } else if (!strcmp(c, "STOP")) {
    streaming = false;
    Serial.println(F("OK STOP"));
  } else if (!strncmp(c, "RATE ", 5)) {
    int hz = atoi(c + 5);
    if (hz < 1) hz = 1;
    if (hz > 100) hz = 100;
    frameMs = 1000 / hz;
    Serial.print(F("OK RATE ")); Serial.println(hz);
  } else if (!strncmp(c, "SIM ", 4)) {
    long rpm = atol(c + 4);
    if (rpm == 0) { simStop(); Serial.println(F("OK SIM OFF")); }
    else if (rpm >= 300 && rpm <= 6000) { simStart(rpm); Serial.print(F("OK SIM ")); Serial.println(rpm); }
    else Serial.println(F("ERR SIM range 300-6000"));
  } else if (cmdLen) {
    Serial.print(F("ERR unknown: ")); Serial.println(c);
  }
}

void readCommands() {
  while (Serial.available()) {
    char ch = Serial.read();
    if (ch == '\r') continue;
    if (ch == '\n') {
      cmd[cmdLen] = 0;
      handleCommand(cmd);
      cmdLen = 0;
    } else if (cmdLen < sizeof(cmd) - 1) {
      cmd[cmdLen++] = toupper(ch);
    }
  }
}

void setup() {
  Serial.begin(115200);
  pinMode(PIN_CRANK, INPUT_PULLUP);  // hall sensor is open collector; add 2.2k external pull-up too
  pinMode(PIN_IGT, INPUT);           // external 100k pull-down keeps it defined
  pinMode(PIN_INJ, INPUT);           // external divider keeps it defined
  simStop();
  attachInterrupt(digitalPinToInterrupt(PIN_CRANK), isrCrank, FALLING);
  attachInterrupt(digitalPinToInterrupt(PIN_IGT), isrIgt, CHANGE);
  PCICR |= (1 << PCIE2);
  PCMSK2 |= (1 << PCINT20);
  resetFrame();
  Serial.println(F(FW_ID));
}

void loop() {
  readCommands();
  if (!streaming) return;
  sampleOne();
  uint32_t nowMs = millis();
  if (nowMs - frameStart >= frameMs) {
    frameStart += frameMs;
    if (nowMs - frameStart > 1000) frameStart = nowMs;  // fell behind, resync
    emitFrame(nowMs);
    resetFrame();
  }
}
