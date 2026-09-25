import argparse
import ctypes
import io
import json
import os
import socket
import struct
import threading
import time
from datetime import datetime

import psutil
from PIL import ImageGrab

from arduino_link import ArduinoLink
from input_sim import SCAN, cs2_running, key_down, key_up, mouse_move

_ard = None
_ard_state = "nao_procurado"
_pad = None


def log(msg):
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def get_arduino():
    global _ard, _ard_state
    if _ard_state == "nao_procurado":
        _ard = ArduinoLink.find()
        if _ard:
            _ard_state = "ok"
            log(f"Saída: Arduino Leonardo ({_ard.port_name}) — hardware real")
        else:
            _ard_state = "sem"
            log("Saída: teclado/rato virtual (software)")
    return _ard if _ard_state == "ok" else None


def do_key(k, hold):
    ard = get_arduino()
    if ard is not None:
        try:
            ard.key(k, hold)
            return
        except Exception:
            log("Arduino desligou-se — a usar software")
            ard.close()
    global _ard, _ard_state
    _ard = None
    _ard_state = "nao_procurado"
    key_down(SCAN[k])
    time.sleep(hold)
    key_up(SCAN[k])


def do_move(dx, dy):
    ard = get_arduino()
    if ard is not None:
        try:
            ard.move(dx, dy)
            return
        except Exception:
            pass
    mouse_move(dx, dy)


def get_pad():
    global _pad
    if _pad is None:
        import vgamepad as vg

        _pad = vg.VX360Gamepad()
        log("Comando virtual Xbox criado (ViGEm)")
    return _pad


def reply(wf, obj):
    wf.write(json.dumps(obj) + "\n")
    wf.flush()


def clamp(v, lo, hi, default):
    try:
        v = int(v)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, v))


class _RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class _BMPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", ctypes.c_uint32),
        ("biWidth", ctypes.c_int32),
        ("biHeight", ctypes.c_int32),
        ("biPlanes", ctypes.c_uint16),
        ("biBitCount", ctypes.c_uint16),
        ("biCompression", ctypes.c_uint32),
        ("biSizeImage", ctypes.c_uint32),
        ("biXPelsPerMeter", ctypes.c_int32),
        ("biYPelsPerMeter", ctypes.c_int32),
        ("biClrUsed", ctypes.c_uint32),
        ("biClrImportant", ctypes.c_uint32),
    ]


def capture_cs2_window():
    from PIL import Image

    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32
    hwnd = user32.FindWindowW(None, "Counter-Strike 2")
    if not hwnd:
        return None
    rect = _RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
        return None
    w, h = rect.right - rect.left, rect.bottom - rect.top
    if w <= 0 or h <= 0:
        return None
    hdc_win = user32.GetDC(hwnd)
    hdc_mem = gdi32.CreateCompatibleDC(hdc_win)
    hbmp = gdi32.CreateCompatibleBitmap(hdc_win, w, h)
    gdi32.SelectObject(hdc_mem, hbmp)
    ok = user32.PrintWindow(hwnd, hdc_mem, 2)
    bi = _BMPINFOHEADER()
    bi.biSize = ctypes.sizeof(_BMPINFOHEADER)
    bi.biWidth = w
    bi.biHeight = -h
    bi.biPlanes = 1
    bi.biBitCount = 32
    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(hdc_mem, hbmp, 0, h, buf, ctypes.byref(bi), 0)
    user32.ReleaseDC(hwnd, hdc_win)
    gdi32.DeleteObject(hbmp)
    gdi32.DeleteDC(hdc_mem)
    if not ok:
        return None
    try:
        return Image.frombuffer("RGBX", (w, h), buf.raw, "raw", "RGBX", 0, 1).convert("RGB")
    except Exception:
        return None


def stream_video(conn, addr, fps, width, q):
    log(f"Vídeo a transmitir para {addr[0]} ({fps} fps)")
    interval = 1.0 / fps
    try:
        while True:
            t0 = time.time()
            try:
                img = capture_cs2_window()
                if img is None:
                    img = ImageGrab.grab()
                w, h = img.size
                nh = max(1, int(h * width / w))
                img = img.convert("RGB").resize((width, nh))
                buf = io.BytesIO()
                img.save(buf, "JPEG", quality=q)
                data = buf.getvalue()
                conn.sendall(struct.pack(">I", len(data)) + data)
            except Exception:
                pass
            dt = time.time() - t0
            if dt < interval:
                time.sleep(interval - dt)
    except Exception:
        pass
    finally:
        conn.close()
        log(f"Vídeo desligado: {addr[0]}")


def handle(conn, addr, token, fps_padrao, width_padrao, q_padrao):
    log(f"Ligação de {addr[0]}")
    authed = False
    try:
        f = conn.makefile("r", encoding="utf-8")
        wf = conn.makefile("w", encoding="utf-8")
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except ValueError:
                reply(wf, {"ok": False, "err": "json"})
                continue
            cmd = msg.get("cmd")
            if not authed:
                if cmd == "auth" and msg.get("token") == token:
                    authed = True
                    reply(wf, {"ok": True})
                    log("PC principal autenticado")
                else:
                    reply(wf, {"ok": False, "err": "auth"})
                    log("Token errado, a desligar")
                    break
                continue
            if cmd == "video":
                fps = clamp(msg.get("fps"), 1, 5, fps_padrao)
                width = clamp(msg.get("width"), 240, 960, width_padrao)
                q = clamp(msg.get("q"), 30, 85, q_padrao)
                reply(wf, {"ok": True, "fps": fps, "width": width})
                wf.flush()
                stream_video(conn, addr, fps, width, q)
                return
            if cmd == "key":
                k = str(msg.get("k", "")).lower()
                hold = float(msg.get("hold", 0.3))
                if k in SCAN and 0 < hold < 5:
                    do_key(k, hold)
                    log(f"Tecla {k.upper()} premida ({hold:.2f}s)")
                    reply(wf, {"ok": True})
                else:
                    reply(wf, {"ok": False, "err": "key"})
            elif cmd == "move":
                dx = int(msg.get("dx", 0))
                dy = int(msg.get("dy", 0))
                do_move(dx, dy)
                log(f"Rato movido ({dx:+d}, {dy:+d})")
                reply(wf, {"ok": True})
            elif cmd == "pad":
                lx = float(msg.get("lx", 0))
                ly = float(msg.get("ly", 0))
                hold = float(msg.get("hold", 0.5))
                try:
                    pad = get_pad()
                    pad.left_joystick_float(lx, ly)
                    pad.update()
                    time.sleep(hold)
                    pad.left_joystick_float(0, 0)
                    pad.update()
                    log(f"Comando: analógica ({lx:+.2f}, {ly:+.2f})")
                    reply(wf, {"ok": True})
                except Exception as e:
                    reply(wf, {"ok": False, "err": str(e)})
            elif cmd == "status":
                ard = get_arduino()
                reply(
                    wf,
                    {
                        "ok": True,
                        "cs2": cs2_running(),
                        "ard": ard is not None,
                    },
                )
            elif cmd == "closecs2":
                n = 0
                for p in psutil.process_iter(["name"]):
                    try:
                        nm = (p.info["name"] or "").lower()
                        if nm in ("cs2.exe", "steam.exe"):
                            p.kill()
                            n += 1
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
                log(f"CS2/Steam fechados ({n} processo(s))")
                reply(wf, {"ok": True, "closed": n})
            elif cmd == "launchcs2":
                try:
                    log("Ordem recebida: a abrir o CS2 via Steam...")
                    os.startfile("steam://rungameid/730")
                    reply(wf, {"ok": True})
                except Exception as e:
                    log(f"Erro ao abrir CS2: {e}")
                    reply(wf, {"ok": False, "err": str(e)})
            elif cmd == "ping":
                reply(wf, {"ok": True})
            elif cmd == "quit":
                break
    except Exception as e:
        log(f"Erro na ligação: {e}")
    finally:
        try:
            conn.close()
        except Exception:
            pass
        log(f"Desligado: {addr[0]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9876)
    ap.add_argument("--token", default="robs")
    ap.add_argument("--fps", type=int, default=2)
    ap.add_argument("--width", type=int, default=480)
    ap.add_argument("--q", type=int, default=60)
    args = ap.parse_args()
    log("=== ROBS FARMER AGENT ===")
    log(f"À escuta na porta {args.port}, à espera do PC principal...")
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", args.port))
    srv.listen()
    while True:
        conn, addr = srv.accept()
        threading.Thread(
            target=handle,
            args=(conn, addr, args.token, args.fps, args.width, args.q),
            daemon=True,
        ).start()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Erro fatal: {e}", flush=True)
    input("Enter para fechar...")
