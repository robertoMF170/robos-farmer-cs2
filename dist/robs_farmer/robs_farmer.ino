#include <Keyboard.h>
#include <Mouse.h>

String buf;

void setup() {
  Serial.begin(115200);
  Keyboard.begin();
  Mouse.begin();
  buf.reserve(64);
}

void loop() {
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\n') {
      handleCmd(buf);
      buf = "";
    } else if (buf.length() < 63) {
      buf += c;
    }
  }
}

void handleCmd(String cmd) {
  cmd.trim();
  if (cmd == "PING") {
    Serial.println("PONG");
    return;
  }
  if (cmd.startsWith("K ")) {
    int sp = cmd.indexOf(' ', 2);
    if (sp < 0) { Serial.println("ERR"); return; }
    String ks = cmd.substring(2, sp);
    int hold = cmd.substring(sp + 1).toInt();
    if (hold < 10) hold = 10;
    if (hold > 5000) hold = 5000;
    char k = tolower(ks.charAt(0));
    if (k != 'w' && k != 'a' && k != 's' && k != 'd') { Serial.println("ERR"); return; }
    Keyboard.press(k);
    delay(hold);
    Keyboard.release(k);
    Serial.println("OK");
    return;
  }
  if (cmd.startsWith("M ")) {
    int sp = cmd.indexOf(' ', 2);
    if (sp < 0) { Serial.println("ERR"); return; }
    int dx = cmd.substring(2, sp).toInt();
    int dy = cmd.substring(sp + 1).toInt();
    if (dx > 120) dx = 120;
    if (dx < -120) dx = -120;
    if (dy > 120) dy = 120;
    if (dy < -120) dy = -120;
    Mouse.move(dx, dy);
    Serial.println("OK");
    return;
  }
  Serial.println("ERR");
}
