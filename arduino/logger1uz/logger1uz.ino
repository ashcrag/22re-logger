// toyota-tap-logger, 1UZ-FE firmware (non-VVTi, 1990-94 LS400 / SC400 computer).
//
// READ ONLY. No pin that connects to the car is ever set as an output.
// The bench simulator pins D9-D13 stay high-impedance (INPUT) unless a SIM
// command turns the simulator on.
//
// Inputs
//   D2  INT0      Ne crank, 12 teeth/rev, via LM393 comparator (tooth = falling edge)
//   D3  INT1      IGT1 (igniter 1: cyl 1,4,6,7), spark on the falling edge
//   D4  PCINT20   IGT2 (igniter 2: cyl 2,3,5,8)
//   D5  PCINT21   one injector group, low side (low = injecting)
//   D6  PCINT22   KS airflow meter frequency (counted on falling edges)
//   D7  PCINT23   G1 cam, once per 2 revs, via LM393 comparator (falling edge)
//   D8  PCINT0    VF1 diagnostic data (TE2 jumped to E1), via comparator; edges are
//                 passed to the laptop as E lines and decoded there
//   A0-A7         VTA, IDL, THW, THA, OX1, OX2, +B, VF1 level (see pc/profiles/p1uz.py)
//
// Serial: 115200 8N1. Commands: ID, PROBE, GO, STOP, RATE <hz>, SIM <rpm>, SIM 0
//
// Frame line (all integers):
//   D,ms,a0..a7,ne_us,g1_teeth,ig1_tooth_us,ig1_toothp_us,ig1_dwell_us,ig1_us,
//     ig2_dwell_us,ig2_us,g1_ph_us,g1_toothp_us,inj_us,inj_n,ks_n,ks_span_us
//   ne_us          last Ne tooth period (30 crank deg), 0 if stalled
//   g1_teeth       Ne teeth between the last G1 pulse and the last IGT1 spark, 255 = no G1
//   ig1_tooth_us   time from the last Ne tooth to that spark; ig1_toothp_us = tooth period then
//   ig1_us/ig2_us  IGT rise-to-rise period (2 per rev each), 0 if stalled
//   g1_ph_us       time from the last Ne tooth to the G1 edge; g1_toothp_us = tooth period then
//   inj_us         average injector on-time over the frame, inj_n pulses
//   ks_n           KS falling edges this frame, ks_span_us = first to last
// VF1 edge line:  E,<micros>,<level after edge>

#include <Arduino.h>

#define FW_ID "TAP-LOGGER 1UZ 0.1"

const uint8_t PIN_NE = 2, PIN_IGT1 = 3, PIN_IGT2 = 4, PIN_INJ = 5, PIN_KS = 6, PIN_G1 = 7, PIN_VF1 = 8;
const uint8_t SIM_PINS[] = {9, 10, 11, 12, 13};  // Ne, G1, IGT1, INJ, KS (PB1..PB5)

const uint8_t N_AN = 8;
const uint8_t AN_PINS[N_AN] = {A0, A1, A2, A3, A4, A5, A6, A7};
const uint8_t NO_G1 = 255;

// ---- capture state ----
volatile uint32_t neLast = 0, nePeriod = 0;
volatile uint8_t teethSinceG = NO_G1;
volatile uint16_t neEdges = 0;

volatile uint32_t g1Last = 0, g1Ph = 0, g1ToothP = 0;
volatile uint16_t g1Edges = 0;

volatile bool ig1High = false;
volatile uint32_t ig1Rise = 0, ig1Period = 0, ig1Dwell = 0, ig1LastEdge = 0;
volatile uint32_t ig1SinceTooth = 0, ig1ToothP = 0;
volatile uint8_t ig1Teeth = NO_G1;
volatile uint16_t ig1Edges = 0;

volatile bool ig2High = false;
volatile uint32_t ig2Rise = 0, ig2Period = 0, ig2Dwell = 0, ig2LastEdge = 0;
volatile uint16_t ig2Edges = 0;

volatile bool injOn = false;
volatile uint32_t injStart = 0, injEnd = 0, injPwSum = 0;
volatile uint16_t injN = 0, injEdges = 0;

volatile uint32_t ksFirst = 0, ksLastT = 0;
volatile uint16_t ksN = 0, ksEdges = 0;

volatile uint8_t pdPrev = 0;

// VF1 edge ring buffer (about 125 edges/s at most)
const uint8_t VF_RING = 32;
volatile uint32_t vfT[VF_RING];
volatile uint8_t vfL[VF_RING];
volatile uint8_t vfHead = 0, vfTail = 0, vfPrev = 2;
volatile uint16_t vfEdges = 0, vfDropped = 0;

void isrNe() {
  uint32_t now = micros();
  if (neLast && now - neLast < 150UL) return;  // faster than 33,000 rpm = noise
  if (neLast) nePeriod = now - neLast;
  neLast = now;
  if (teethSinceG < 254) teethSinceG++;
  neEdges++;
}

void isrIgt1() {
  uint32_t now = micros();
  bool lv = PIND & (1 << 3);
  ig1Edges++;
  if (lv && !ig1High) {
    ig1High = true;
    if (ig1Rise) ig1Period = now - ig1Rise;
    ig1Rise = now;
    ig1LastEdge = now;
  } else if (!lv && ig1High) {
    if (now - ig1Rise < 200UL) return;
    ig1High = false;
    ig1Dwell = now - ig1Rise;
    ig1LastEdge = now;
    ig1Teeth = (g1Last && now - g1Last < 2000000UL) ? teethSinceG : NO_G1;
    ig1SinceTooth = neLast ? now - neLast : 0;
    ig1ToothP = nePeriod;
  }
}

static inline void igt2Edge(uint32_t now, bool lv) {
  ig2Edges++;
  if (lv && !ig2High) {
    ig2High = true;
    if (ig2Rise) ig2Period = now - ig2Rise;
    ig2Rise = now;
    ig2LastEdge = now;
  } else if (!lv && ig2High) {
    if (now - ig2Rise < 200UL) return;
    ig2High = false;
    ig2Dwell = now - ig2Rise;
    ig2LastEdge = now;
  }
}

static inline void injEdge(uint32_t now, bool lv) {
  if (!lv && !injOn) {
    if (injEnd && now - injEnd < 500UL) return;  // flyback ringing after close
    injOn = true;
    injStart = now;
    injEdges++;
  } else if (lv && injOn) {
    if (now - injStart < 200UL) return;
    injOn = false;
    injEnd = now;
    injPwSum += now - injStart;
    injN++;
    injEdges++;
  }
}

static inline void g1Fall(uint32_t now) {
  if (g1Last && now - g1Last < 10000UL) return;  // once per 2 revs; closer than 10 ms = noise
  g1Last = now;
  g1Ph = neLast ? now - neLast : 0;
  g1ToothP = nePeriod;
  teethSinceG = 0;
  g1Edges++;
}

ISR(PCINT2_vect) {
  uint32_t now = micros();
  uint8_t pd = PIND;
  uint8_t ch = pd ^ pdPrev;
  pdPrev = pd;
  if (ch & (1 << 4)) igt2Edge(now, pd & (1 << 4));
  if (ch & (1 << 5)) injEdge(now, pd & (1 << 5));
  if ((ch & (1 << 6)) && !(pd & (1 << 6))) {
    if (ksN == 0) ksFirst = now;
    ksLastT = now;
    ksN++;
    ksEdges++;
  }
  if ((ch & (1 << 7)) && !(pd & (1 << 7))) g1Fall(now);
}

ISR(PCINT0_vect) {
  uint32_t now = micros();
  uint8_t lv = PINB & 1;
  if (lv == vfPrev) return;
  vfPrev = lv;
  vfEdges++;
  uint8_t next = (vfHead + 1) % VF_RING;
  if (next == vfTail) { vfDropped++; return; }
  vfT[vfHead] = now;
  vfL[vfHead] = lv;
  vfHead = next;
}

// ---- bench simulator: Timer2 at 20 kHz (50 us ticks), one 720 deg cycle ----
const uint32_t SIM_TICK = 50, SIM_PULSE = 300, SIM_DWELL = 3000, SIM_INJ_PW = 2500, SIM_KS_HALF = 5000;
volatile uint32_t simPeriod = 0, simPhase = 0, simTooth = 0, simToothPh = 0, simKsPh = 0;
volatile uint32_t simG1 = 0, simInj = 0, simSpark[4];
volatile bool simKs = true;

ISR(TIMER2_COMPA_vect) {
  uint32_t p = simPhase + SIM_TICK;
  if (p >= simPeriod) p -= simPeriod;
  simPhase = p;
  uint32_t tp = simToothPh + SIM_TICK;
  if (tp >= simTooth) tp -= simTooth;
  simToothPh = tp;
  uint32_t kp = simKsPh + SIM_TICK;
  if (kp >= SIM_KS_HALF) { kp -= SIM_KS_HALF; simKs = !simKs; }
  simKsPh = kp;

  uint8_t out = PORTB & ~0x3E;               // PB1..PB5
  if (tp >= SIM_PULSE) out |= (1 << 1);     // Ne: low pulse at every tooth
  if (!(p >= simG1 && p < simG1 + SIM_PULSE)) out |= (1 << 2);  // G1: low pulse once per cycle
  for (uint8_t i = 0; i < 4; i++)
    if (p + SIM_DWELL >= simSpark[i] && p < simSpark[i]) { out |= (1 << 3); break; }  // IGT1 dwell
  if (!(p >= simInj && p < simInj + SIM_INJ_PW)) out |= (1 << 4);  // injector low = on
  if (simKs) out |= (1 << 5);
  PORTB = out;
}

void simStop() {
  TIMSK2 = 0;
  simPeriod = 0;
  for (uint8_t i = 0; i < sizeof(SIM_PINS); i++) pinMode(SIM_PINS[i], INPUT);
}

void simStart(uint32_t rpm) {
  simStop();
  if (rpm < 300 || rpm > 6000) return;
  uint32_t cycle = 120000000UL / rpm;  // 720 crank degrees
  noInterrupts();
  simPeriod = cycle;
  simPhase = 0;
  simTooth = cycle / 24;               // 30 deg
  simToothPh = 0;
  simG1 = simTooth / 2;                // halfway between two teeth
  for (uint8_t i = 0; i < 4; i++) simSpark[i] = cycle / 72UL * (17UL + 18UL * i);  // 170,350,530,710 deg
  simInj = cycle / 8;                  // 90 deg
  simKsPh = 0;
  interrupts();
  for (uint8_t i = 0; i < sizeof(SIM_PINS); i++) {
    digitalWrite(SIM_PINS[i], i == 2 ? LOW : HIGH);
    pinMode(SIM_PINS[i], OUTPUT);
  }
  TCCR2A = (1 << WGM21);
  TCCR2B = (1 << CS21);
  OCR2A = 99;
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
  Serial.println(F("H,ms,a0,a1,a2,a3,a4,a5,a6,a7,ne_us,g1_teeth,ig1_tooth_us,ig1_toothp_us,ig1_dwell_us,ig1_us,"
                   "ig2_dwell_us,ig2_us,g1_ph_us,g1_toothp_us,inj_us,inj_n,ks_n,ks_span_us"));
}

void pv(uint32_t v) { Serial.print(','); Serial.print(v); }

void emitFrame(uint32_t nowMs) {
  uint32_t now = micros();
  noInterrupts();
  uint32_t nP = nePeriod, nL = neLast;
  uint8_t teeth = ig1Teeth;
  uint32_t sinceT = ig1SinceTooth, tP = ig1ToothP, d1 = ig1Dwell, p1 = ig1Period, l1 = ig1LastEdge;
  uint32_t d2 = ig2Dwell, p2 = ig2Period, l2 = ig2LastEdge;
  uint32_t gPh = g1Ph, gTp = g1ToothP, gL = g1Last;
  uint32_t pw = injPwSum;
  uint16_t n = injN;
  uint16_t kn = ksN;
  uint32_t kspan = ksLastT - ksFirst;
  injPwSum = 0; injN = 0; ksN = 0;
  interrupts();
  if (!nL || now - nL > 1000000UL) nP = 0;
  if (!l1 || now - l1 > 1000000UL) { p1 = 0; d1 = 0; teeth = NO_G1; sinceT = 0; tP = 0; }
  if (!l2 || now - l2 > 1000000UL) { p2 = 0; d2 = 0; }
  if (!gL || now - gL > 2000000UL) { gPh = 0; gTp = 0; }
  if (kn < 2) kspan = 0;
  Serial.print('D'); Serial.print(','); Serial.print(nowMs);
  for (uint8_t i = 0; i < N_AN; i++) pv(anCnt[i] ? (anSum[i] + anCnt[i] / 2) / anCnt[i] : 0);
  pv(nP); pv(teeth); pv(sinceT); pv(tP); pv(d1); pv(p1); pv(d2); pv(p2); pv(gPh); pv(gTp);
  pv(n ? pw / n : 0); pv(n); pv(kn); pv(kspan);
  Serial.println();
}

void flushVf1() {
  while (true) {
    noInterrupts();
    if (vfTail == vfHead) { interrupts(); return; }
    uint32_t t = vfT[vfTail];
    uint8_t l = vfL[vfTail];
    vfTail = (vfTail + 1) % VF_RING;
    interrupts();
    Serial.print(F("E,")); Serial.print(t); Serial.print(','); Serial.println(l);
  }
}

void doProbe() {
  uint16_t mn[N_AN], mx[N_AN];
  uint32_t sum[N_AN];
  uint16_t cnt[N_AN];
  for (uint8_t i = 0; i < N_AN; i++) { mn[i] = 1023; mx[i] = 0; sum[i] = 0; cnt[i] = 0; }
  volatile uint16_t *ctr[] = {&neEdges, &ig1Edges, &ig2Edges, &injEdges, &ksEdges, &g1Edges, &vfEdges};
  const uint8_t pins[] = {PIN_NE, PIN_IGT1, PIN_IGT2, PIN_INJ, PIN_KS, PIN_G1, PIN_VF1};
  uint16_t start[7];
  noInterrupts();
  for (uint8_t i = 0; i < 7; i++) start[i] = *ctr[i];
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
  for (uint8_t i = 0; i < N_AN; i++) {
    Serial.print(F("P,A")); Serial.print(i);
    pv(mn[i]); pv(mx[i]); pv(cnt[i] ? sum[i] / cnt[i] : 0);
    Serial.println();
  }
  for (uint8_t i = 0; i < 7; i++) {
    noInterrupts();
    uint16_t now = *ctr[i];
    interrupts();
    Serial.print(F("P,D")); Serial.print(pins[i]);
    pv((uint16_t)(now - start[i])); pv(digitalRead(pins[i]));
    Serial.println();
  }
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
    noInterrupts();
    vfTail = vfHead;  // start the VF1 stream fresh
    interrupts();
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
  // comparator outputs are open collector: internal pull-ups plus the external ones in docs/1uz/hardware.md
  pinMode(PIN_NE, INPUT_PULLUP);
  pinMode(PIN_G1, INPUT_PULLUP);
  pinMode(PIN_VF1, INPUT_PULLUP);
  pinMode(PIN_IGT1, INPUT);  // external 100k pull-downs keep these defined
  pinMode(PIN_IGT2, INPUT);
  pinMode(PIN_INJ, INPUT);   // external divider keeps it defined
  pinMode(PIN_KS, INPUT);    // external divider keeps it defined
  simStop();
  pdPrev = PIND;
  vfPrev = PINB & 1;
  attachInterrupt(digitalPinToInterrupt(PIN_NE), isrNe, FALLING);
  attachInterrupt(digitalPinToInterrupt(PIN_IGT1), isrIgt1, CHANGE);
  PCICR |= (1 << PCIE2) | (1 << PCIE0);
  PCMSK2 |= (1 << PCINT20) | (1 << PCINT21) | (1 << PCINT22) | (1 << PCINT23);
  PCMSK0 |= (1 << PCINT0);
  resetFrame();
  Serial.println(F(FW_ID));
}

void loop() {
  readCommands();
  if (!streaming) return;
  flushVf1();
  sampleOne();
  uint32_t nowMs = millis();
  if (nowMs - frameStart >= frameMs) {
    frameStart += frameMs;
    if (nowMs - frameStart > 1000) frameStart = nowMs;
    emitFrame(nowMs);
    resetFrame();
  }
}
