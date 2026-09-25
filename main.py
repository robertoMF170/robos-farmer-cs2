import ctypes
import ctypes.wintypes
import datetime
import io
import json
import os
import random
import socket
import struct
import sys
import threading
import time
import tkinter as tk

import customtkinter as ctk
import psutil
from PIL import Image

from arduino_link import ArduinoLink
from input_sim import SCAN, key_down, key_up, mouse_move

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

user32 = ctypes.windll.user32

WM_HOTKEY = 0x0312
VK_F8 = 0x77
HOTKEY_ID = 0xB00B
PORTA_PADRAO = 9876
CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.abspath(sys.argv[0])), "farmer_config.json"
)

COR_FUNDO = "#16161b"
COR_PAINEL = "#1f1f26"
COR_PAINEL2 = "#26262f"
COR_TEXTO = "#e6e6ec"
COR_TEXTO2 = "#8a8a96"
COR_ACENTO = "#f0a832"
COR_ACENTO_HOVER = "#c9871e"
COR_VERDE = "#4cc94c"
COR_VERMELHO = "#d64545"
COR_AZUL = "#4da6ff"


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("CS2 Robs Farmer")
        self.geometry("900x650")
        self.minsize(820, 610)
        self.configure(fg_color=COR_FUNDO)
        self._dark_titlebar()

        self.running = False
        self.thread = None
        self.all_procs = []
        self.displayed = []
        self.cs2_found = False
        self._was_found = False
        self.remote_sock = None
        self.remote_file = None
        self.remote_lock = threading.Lock()
        self.video_on = False
        self.video_sock = None
        self.video_thread = None
        self._video_img = None
        self._modo_jogar = False
        self._resume_when_found = False
        self._ard = None
        self._ard_state = "nao_procurado"
        self._pad = None

        cfg = self._load_config()
        destino_cfg = cfg.get("destino", "Local")
        if destino_cfg == "Remoto":
            destino_cfg = "Remoto"
        self.destino_var = ctk.StringVar(value=destino_cfg)
        self.host_var = ctk.StringVar(
            value=cfg.get("host") or "100.93.247.111"
        )
        self.token_var = ctk.StringVar(value=cfg.get("token", "robs"))
        self._destino_txt = self.destino_var.get()
        self._host_txt = self.host_var.get().strip()
        self._token_txt = self.token_var.get().strip() or "robs"

        args = sys.argv[1:]
        self.auto = "--auto" in args

        self._build_ui()
        self.destino_var.trace_add("write", lambda *a: self._on_destino())
        self.host_var.trace_add("write", lambda *a: self._save_config())
        self.token_var.trace_add("write", lambda *a: self._save_config())
        for v in (self.destino_var, self.host_var, self.token_var):
            v.trace_add("write", lambda *a: self._sync_vars())
        self._sync_vars()
        self._apply_destino()
        if self.auto:
            self._log("Modo automático ativo: vou começar quando o cs2.exe aparecer.")
        self.after(30000, self._auto_rescan)
        if "--min" in args:
            self.after(200, self.iconify)
        self.refresh_processes()
        threading.Thread(target=self._hotkey_loop, daemon=True).start()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _dark_titlebar(self):
        try:
            hwnd = user32.GetParent(self.winfo_id())
            value = ctypes.c_int(1)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, 20, ctypes.byref(value), ctypes.sizeof(value)
            )
        except Exception:
            pass

    def _load_config(self):
        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_config(self):
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "destino": self.destino_var.get(),
                        "host": self.host_var.get(),
                        "token": self.token_var.get(),
                    },
                    f,
                    ensure_ascii=False,
                )
        except Exception:
            pass

    def _build_ui(self):
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=24, pady=(18, 8))

        title = ctk.CTkFont(family="Segoe UI", size=26, weight="bold")
        sub = ctk.CTkFont(family="Segoe UI", size=12)

        ctk.CTkLabel(header, text="CS2 ", font=title, text_color=COR_TEXTO).grid(
            row=0, column=0, sticky="w"
        )
        ctk.CTkLabel(
            header, text="ROBS FARMER", font=title, text_color=COR_ACENTO
        ).grid(row=0, column=1, sticky="w")
        ctk.CTkLabel(
            header,
            text="   Anti-AFK  •  Local ou destino remoto (Ally / sessão fantasma)  •  F8 inicia/para",
            font=sub,
            text_color=COR_TEXTO2,
        ).grid(row=0, column=2, sticky="w", padx=(4, 0))

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=24, pady=(4, 20))
        body.grid_columnconfigure(0, weight=3)
        body.grid_columnconfigure(1, weight=2)
        body.grid_rowconfigure(0, weight=1)

        left = ctk.CTkFrame(body, fg_color=COR_PAINEL, corner_radius=14)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 12))

        ctk.CTkLabel(
            left,
            text="PROCESSOS ATIVOS (LOCAL)",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=COR_TEXTO2,
        ).pack(anchor="w", padx=16, pady=(14, 6))
        self.list_title = left.winfo_children()[-1]

        search_row = ctk.CTkFrame(left, fg_color="transparent")
        search_row.pack(fill="x", padx=16)
        search_row.grid_columnconfigure(0, weight=1)
        self.search_row = search_row

        self.search_var = ctk.StringVar()
        self.search_var.trace_add("write", lambda *a: self._filter())
        self.search_entry = ctk.CTkEntry(
            search_row,
            textvariable=self.search_var,
            placeholder_text="Procurar processo...",
            height=34,
            fg_color=COR_PAINEL2,
            border_width=0,
        )
        self.search_entry.grid(row=0, column=0, sticky="ew")

        self.refresh_btn = ctk.CTkButton(
            search_row,
            text="⟳",
            width=40,
            height=34,
            fg_color=COR_PAINEL2,
            hover_color="#33333f",
            command=self.refresh_processes,
        )
        self.refresh_btn.grid(row=0, column=1, padx=(8, 0))

        list_frame = ctk.CTkFrame(left, fg_color="transparent")
        list_frame.pack(fill="both", expand=True, padx=16, pady=12)
        list_frame.grid_columnconfigure(0, weight=1)
        list_frame.grid_rowconfigure(0, weight=1)
        self.list_frame = list_frame

        self.listbox = tk.Listbox(
            list_frame,
            bg=COR_PAINEL2,
            fg=COR_TEXTO,
            selectbackground=COR_ACENTO,
            selectforeground="#16161b",
            highlightthickness=0,
            relief="flat",
            activestyle="none",
            font=("Segoe UI", 11),
        )
        self.listbox.grid(row=0, column=0, sticky="nsew")
        self.listbox.bind("<<ListboxSelect>>", self._on_select)

        scrollbar = ctk.CTkScrollbar(list_frame, command=self.listbox.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.listbox.configure(yscrollcommand=scrollbar.set)

        self.proc_status = ctk.CTkLabel(
            left,
            text="●  À procura do cs2.exe...",
            font=ctk.CTkFont(size=12),
            text_color=COR_TEXTO2,
        )
        self.proc_status.pack(anchor="w", padx=16, pady=(0, 12))

        self.video_label = ctk.CTkLabel(
            left,
            text="A LIGAR AO VÍDEO DO DESTINO REMOTO...",
            fg_color=COR_PAINEL2,
            corner_radius=10,
            height=340,
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=COR_TEXTO2,
        )
        self.stream_status = ctk.CTkLabel(
            left,
            text="●  Vídeo: desligado",
            font=ctk.CTkFont(size=12),
            text_color=COR_TEXTO2,
        )

        right = ctk.CTkFrame(body, fg_color=COR_PAINEL, corner_radius=14)
        right.grid(row=0, column=1, sticky="nsew")

        ctk.CTkLabel(
            right,
            text="DESTINO DOS INPUTS",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=COR_TEXTO2,
        ).pack(anchor="w", padx=16, pady=(14, 4))

        ctk.CTkSegmentedButton(
            right,
            values=["Local", "Remoto"],
            variable=self.destino_var,
            selected_color=COR_AZUL,
            selected_hover_color="#3a8ad6",
            unselected_color=COR_PAINEL2,
            unselected_hover_color="#33333f",
            fg_color=COR_PAINEL2,
            height=28,
        ).pack(fill="x", padx=16)

        ally_box = ctk.CTkFrame(right, fg_color="transparent")
        ally_box.pack(fill="x", padx=16, pady=(8, 0))
        ally_box.grid_columnconfigure(0, weight=1)

        self.host_entry = ctk.CTkEntry(
            ally_box,
            textvariable=self.host_var,
            placeholder_text="IP do destino (127.0.0.1 = sessão fantasma)",
            height=30,
            fg_color=COR_PAINEL2,
            border_width=0,
        )
        self.host_entry.grid(row=0, column=0, sticky="ew")

        self.token_entry = ctk.CTkEntry(
            ally_box,
            textvariable=self.token_var,
            placeholder_text="Token",
            height=30,
            width=90,
            fg_color=COR_PAINEL2,
            border_width=0,
        )
        self.token_entry.grid(row=0, column=1, padx=(8, 0))

        ctk.CTkLabel(
            right,
            text="ALVO",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=COR_TEXTO2,
        ).pack(anchor="w", padx=16, pady=(14, 2))

        self.selected_label = ctk.CTkLabel(
            right,
            text="Nenhum processo selecionado",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=COR_TEXTO,
        )
        self.selected_label.pack(anchor="w", padx=16)

        ctk.CTkLabel(
            right,
            text="INTERVALO ENTRE AÇÕES",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=COR_TEXTO2,
        ).pack(anchor="w", padx=16, pady=(14, 2))

        self.interval_var = ctk.IntVar(value=20)
        self.interval_label = ctk.CTkLabel(
            right,
            text="20 segundos",
            font=ctk.CTkFont(size=13),
            text_color=COR_ACENTO,
        )
        self.interval_label.pack(anchor="w", padx=16)
        ctk.CTkSlider(
            right,
            from_=5,
            to=60,
            number_of_steps=55,
            variable=self.interval_var,
            progress_color=COR_ACENTO,
            button_color=COR_ACENTO,
            button_hover_color=COR_ACENTO_HOVER,
            command=self._on_interval,
        ).pack(fill="x", padx=16, pady=(2, 0))

        ctk.CTkLabel(
            right,
            text="AÇÃO",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=COR_TEXTO2,
        ).pack(anchor="w", padx=16, pady=(14, 4))

        self.mode_var = ctk.StringVar(value="WASD")
        ctk.CTkSegmentedButton(
            right,
            values=["WASD", "Rato", "Ambos", "Comando"],
            variable=self.mode_var,
            selected_color=COR_ACENTO,
            selected_hover_color=COR_ACENTO_HOVER,
            unselected_color=COR_PAINEL2,
            unselected_hover_color="#33333f",
            fg_color=COR_PAINEL2,
            height=28,
        ).pack(fill="x", padx=16)

        self.play_btn = ctk.CTkButton(
            right,
            text="▶   INICIAR",
            font=ctk.CTkFont(size=17, weight="bold"),
            height=48,
            corner_radius=12,
            fg_color=COR_ACENTO,
            hover_color=COR_ACENTO_HOVER,
            text_color="#16161b",
            command=self.toggle,
        )
        self.play_btn.pack(fill="x", padx=16, pady=(16, 8))

        self.status_dot = ctk.CTkLabel(
            right,
            text="●  PARADO",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#77777f",
        )
        self.status_dot.pack(anchor="w", padx=16)

        self.liberar_btn = ctk.CTkButton(
            right,
            text="🎮   LIBERAR CONTA PARA JOGAR NO PC",
            font=ctk.CTkFont(size=13, weight="bold"),
            height=36,
            corner_radius=10,
            fg_color=COR_AZUL,
            hover_color="#3a8ad6",
            command=self.liberar_conta,
        )
        self.liberar_btn.pack(fill="x", padx=16, pady=(8, 0), after=self.status_dot)

        ctk.CTkLabel(
            right,
            text="REGISTO",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=COR_TEXTO2,
        ).pack(anchor="w", padx=16, pady=(12, 2))

        self.log_box = ctk.CTkTextbox(
            right,
            height=120,
            fg_color=COR_PAINEL2,
            border_width=0,
            font=ctk.CTkFont(family="Consolas", size=12),
            text_color="#b9b9c4",
        )
        self.log_box.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        self.log_box.configure(state="disabled")

    def _sync_vars(self):
        self._destino_txt = self.destino_var.get()
        self._host_txt = self.host_var.get().strip()
        self._token_txt = self.token_var.get().strip() or "robs"

    def _on_destino(self):
        self._save_config()
        self._apply_destino()
        self.refresh_processes()

    def _apply_destino(self):
        remoto = self.destino_var.get() == "Remoto"
        state = "disabled" if remoto else "normal"
        self.search_entry.configure(state=state)
        self.listbox.configure(
            state=state,
            selectbackground=COR_PAINEL2 if remoto else COR_ACENTO,
        )
        self.host_entry.configure(
            fg_color=COR_PAINEL2 if remoto else "#1c1c22",
            text_color=COR_TEXTO if remoto else COR_TEXTO2,
        )
        if remoto:
            self.list_title.configure(text="REMOTO — ECRÃ AO VIVO")
            self.search_row.pack_forget()
            self.list_frame.pack_forget()
            self.video_label.pack(fill="both", expand=True, padx=16, pady=(6, 4))
            self.stream_status.pack(anchor="w", padx=16, pady=(0, 8))
            self.liberar_btn.pack(fill="x", padx=16, pady=(8, 0), after=self.status_dot)
            self.proc_status.configure(text="●  A ligar ao destino remoto...", text_color=COR_AZUL)
            self.selected_label.configure(text="Destino remoto")
            self._start_video()
        else:
            self.list_title.configure(text="PROCESSOS ATIVOS (LOCAL)")
            self.video_label.pack_forget()
            self.stream_status.pack_forget()
            self.liberar_btn.pack_forget()
            self.search_row.pack(fill="x", padx=16)
            self.list_frame.pack(fill="both", expand=True, padx=16, pady=12)
            self.proc_status.configure(
                text="●  À procura do cs2.exe...", text_color=COR_TEXTO2
            )
            self._stop_video()

    def _on_interval(self, value):
        self.interval_label.configure(text=f"{int(value)} segundos")

    def refresh_processes(self):
        if self.destino_var.get() == "Remoto":
            threading.Thread(target=self._remote_scan, daemon=True).start()
        else:
            self.refresh_btn.configure(state="disabled")
            self.proc_status.configure(text="●  A procurar...", text_color=COR_TEXTO2)
            threading.Thread(target=self._scan, daemon=True).start()

    def _scan(self):
        procs = []
        for p in psutil.process_iter(["pid", "name"]):
            try:
                name = p.info["name"] or ""
                if name.lower().endswith(".exe"):
                    procs.append((p.info["pid"], name))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        procs.sort(key=lambda x: x[1].lower())
        self.all_procs = procs
        self.after(0, self._fill_list)

    def _filter(self):
        self._fill_list()

    def _fill_list(self):
        if self.destino_var.get() == "Remoto":
            return
        query = self.search_var.get().lower().strip()
        self.listbox.delete(0, "end")
        self.displayed = []
        self.cs2_found = False
        cs2_index = None
        for pid, name in self.all_procs:
            if query and query not in name.lower():
                continue
            self.listbox.insert("end", f"  {name}   (PID {pid})")
            self.displayed.append((pid, name))
            if name.lower() == "cs2.exe":
                self.cs2_found = True
                cs2_index = len(self.displayed) - 1
                self.listbox.itemconfigure(cs2_index, foreground=COR_ACENTO)
        self.refresh_btn.configure(state="normal")
        if self.cs2_found:
            self.proc_status.configure(
                text="●  cs2.exe DETETADO", text_color=COR_VERDE
            )
            self.listbox.selection_clear(0, "end")
            self.listbox.selection_set(cs2_index)
            self.listbox.see(cs2_index)
            self._update_selected(cs2_index)
            if self.auto and not self._was_found and not self.running:
                self._log("Modo automático: cs2.exe detetado, a iniciar farm.")
                self.start()
        else:
            self.proc_status.configure(
                text="●  cs2.exe NÃO ENCONTRADO", text_color=COR_VERMELHO
            )
        self._was_found = self.cs2_found

    def _remote_scan(self):
        found, ard = self._remote_status()
        self.after(0, lambda: self._fill_remote(found, ard))

    def _fill_remote(self, found, ard=False):
        sufixo = "  •  Saída: Arduino" if ard else ""
        self.cs2_found = found
        if found:
            self.proc_status.configure(
                text="●  cs2.exe DETETADO no destino remoto", text_color=COR_VERDE
            )
            self.selected_label.configure(
                text=f"cs2.exe no destino remoto{sufixo}", text_color=COR_AZUL
            )
            if (
                (self.auto or self._resume_when_found)
                and not self._was_found
                and not self.running
            ):
                self._resume_when_found = False
                self._log("CS2 aberto no destino, a retomar o farm sozinho.")
                self.start()
                self._atualizar_botao_liberar()
        else:
            self.proc_status.configure(
                text="●  cs2.exe NÃO ENCONTRADO no destino remoto", text_color=COR_VERMELHO
            )
            self.selected_label.configure(
                text="À espera do cs2.exe no destino remoto...", text_color=COR_TEXTO
            )
        self._was_found = found

    def _on_select(self, _event):
        sel = self.listbox.curselection()
        if sel:
            self._update_selected(sel[0])

    def _update_selected(self, index):
        if 0 <= index < len(self.displayed):
            pid, name = self.displayed[index]
            self.selected_label.configure(text=f"{name}  (PID {pid})")

    def _remote_disconnect(self):
        try:
            if self.remote_file:
                self.remote_file.close()
            if self.remote_sock:
                self.remote_sock.close()
        except Exception:
            pass
        self.remote_sock = None
        self.remote_file = None

    def _remote_connect(self):
        host = self._host_txt
        token = self._token_txt
        if not host:
            raise ValueError("Indica o IP do destino no campo 'IP do destino'")
        sock = socket.create_connection((host, PORTA_PADRAO), timeout=5)
        sock.settimeout(None)
        self.remote_sock = sock
        self.remote_file = sock.makefile("r", encoding="utf-8")
        self._remote_send({"cmd": "auth", "token": token})
        line = self.remote_file.readline()
        resp = json.loads(line) if line else {}
        if not resp.get("ok"):
            self._remote_disconnect()
            raise ValueError("Token recusado pelo destino")

    def _remote_send(self, obj):
        self.remote_sock.sendall((json.dumps(obj) + "\n").encode("utf-8"))

    def _remote_cmd(self, obj):
        with self.remote_lock:
            if self.remote_sock is None:
                self._remote_connect()
            try:
                self._remote_send(obj)
                line = self.remote_file.readline()
            except (OSError, ValueError):
                self._remote_disconnect()
                self._remote_connect()
                self._remote_send(obj)
                line = self.remote_file.readline()
            if not line:
                self._remote_disconnect()
                raise ConnectionError("O destino remoto desligou-se")
            return json.loads(line)

    def _remote_status(self):
        try:
            r = self._remote_cmd({"cmd": "status"})
            return bool(r.get("cs2")), bool(r.get("ard"))
        except Exception as e:
            self._log(f"Erro remoto: {e}")
            return False, False

    def _start_video(self):
        if self.video_thread and self.video_thread.is_alive():
            return
        self.video_on = True
        self.video_thread = threading.Thread(target=self._video_loop, daemon=True)
        self.video_thread.start()

    def _stop_video(self):
        self.video_on = False
        try:
            if self.video_sock:
                self.video_sock.close()
        except Exception:
            pass
        self.video_sock = None
        self._video_img = None
        self.after(
            0,
            lambda: self.video_label.configure(
                text="A LIGAR AO VÍDEO DO DESTINO REMOTO...", image=None
            ),
        )
        self.after(
            0,
            lambda: self.stream_status.configure(
                text="●  Vídeo: desligado", text_color=COR_TEXTO2
            ),
        )

    @staticmethod
    def _recv_exact(sock, n):
        buf = b""
        while len(buf) < n:
            chunk = sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("stream fechado")
            buf += chunk
        return buf

    def _video_loop(self):
        while self.video_on and self._destino_txt == "Remoto":
            sock = None
            try:
                host = self._host_txt
                token = self._token_txt
                if not host:
                    raise ValueError("IP do destino em falta")
                sock = socket.create_connection((host, PORTA_PADRAO), timeout=5)
                sock.settimeout(15)
                self.video_sock = sock
                f = sock.makefile("r", encoding="utf-8")
                sock.sendall(
                    (json.dumps({"cmd": "auth", "token": token}) + "\n").encode()
                )
                if not json.loads(f.readline() or "{}").get("ok"):
                    raise ValueError("Token recusado")
                sock.sendall(
                    (
                        json.dumps(
                            {"cmd": "video", "fps": 2, "width": 480, "q": 60}
                        )
                        + "\n"
                    ).encode()
                )
                ack = json.loads(f.readline() or "{}")
                if not ack.get("ok"):
                    raise ValueError("O destino recusou o vídeo")
                self.after(
                    0,
                    lambda: self.stream_status.configure(
                        text=f"●  Vídeo ao vivo  •  {ack.get('fps', 2)} fps",
                        text_color=COR_VERDE,
                    ),
                )
                while self.video_on:
                    (n,) = struct.unpack(">I", self._recv_exact(sock, 4))
                    data = self._recv_exact(sock, n)
                    self.after(0, self._show_frame, data)
            except Exception as e:
                if self.video_on:
                    msg = str(e)
                    self.after(
                        0,
                        lambda: self.stream_status.configure(
                            text=f"●  Vídeo: {msg} — a tentar de novo...",
                            text_color=COR_VERMELHO,
                        ),
                    )
            try:
                if sock:
                    sock.close()
            except Exception:
                pass
            self.video_sock = None
            if self.video_on and self._destino_txt == "Remoto":
                time.sleep(5)

    def _show_frame(self, data):
        if not self.video_on:
            return
        try:
            img = Image.open(io.BytesIO(data))
            self._video_img = ctk.CTkImage(light_image=img, size=img.size)
            self.video_label.configure(image=self._video_img, text="")
        except Exception:
            pass

    def _atualizar_botao_liberar(self):
        if self._modo_jogar:
            self.liberar_btn.configure(
                text="🔁   VOLTAR AO FARM REMOTO (abre o CS2 lá)",
                fg_color=COR_VERDE,
                hover_color="#3aa53a",
            )
            self.status_dot.configure(
                text="●  MODO JOGAR NO PC", text_color=COR_AZUL
            )
        else:
            self.liberar_btn.configure(
                text="🎮   LIBERAR CONTA PARA JOGAR NO PC",
                fg_color=COR_AZUL,
                hover_color="#3a8ad6",
            )
            if not self.running:
                self.status_dot.configure(text="●  PARADO", text_color="#77777f")

    def liberar_conta(self):
        if self.destino_var.get() != "Remoto":
            return
        if not self._modo_jogar:
            if self.running:
                self.stop()
                self._log("Farm parado.")
            self._log("A fechar o CS2 no destino remoto...")

            def worker():
                try:
                    r = self._remote_cmd({"cmd": "closecs2"})
                    n = r.get("closed", 0)
                    if n:
                        self._log(
                            f"CS2/Steam fechados no destino ({n}). Conta livre para o PC."
                        )
                    else:
                        self._log("O CS2 já não estava aberto no destino.")
                    self._modo_jogar = True
                    self._resume_when_found = False
                    self.after(0, self._atualizar_botao_liberar)
                except Exception as e:
                    self._log(f"Erro ao fechar CS2 no destino: {e}")

            threading.Thread(target=worker, daemon=True).start()
        else:
            self._log("A abrir o CS2 no destino remoto...")

            def worker2():
                try:
                    self._remote_cmd({"cmd": "launchcs2"})
                    self._resume_when_found = True
                    self._modo_jogar = False
                    self._log(
                        "Ordem enviada. Quando o CS2 abrir no destino, o farm retoma sozinho."
                    )
                    self.after(0, self._atualizar_botao_liberar)
                except Exception as e:
                    self._log(f"Erro ao abrir CS2 no destino: {e}")

            threading.Thread(target=worker2, daemon=True).start()

    def toggle(self):
        if self.running:
            self.stop()
        else:
            self.start()

    def start(self):
        if self.running:
            return
        remoto = self.destino_var.get() == "Remoto"
        if not remoto and not self.cs2_found:
            self._log("Aviso: cs2.exe não foi encontrado, mas vou continuar.")
        self.running = True
        self.play_btn.configure(
            text="⏹   PARAR", fg_color=COR_VERMELHO, hover_color="#a83535"
        )
        alvo = "REMOTO" if remoto else "LOCAL"
        self.status_dot.configure(
            text=f"●  A FARMAR {alvo}", text_color=COR_VERDE
        )
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        self.play_btn.configure(
            text="▶   INICIAR", fg_color=COR_ACENTO, hover_color=COR_ACENTO_HOVER
        )
        self.status_dot.configure(text="●  PARADO", text_color="#77777f")

    def _detect_local_output(self):
        if self._ard_state == "nao_procurado":
            self._ard = ArduinoLink.find()
            if self._ard:
                self._ard_state = "ok"
                self._log(
                    f"Saída: ARDUINO LEONARDO ({self._ard.port_name}) — hardware real, "
                    "rato e teclado do PC livres."
                )
            else:
                self._ard_state = "sem"
                self._log(
                    "Saída: teclado/rato do PC (software). Liga o Arduino para hardware real."
                )

    def _local_key(self, key, hold):
        self._detect_local_output()
        if self._ard_state == "ok":
            try:
                self._ard.key(key, hold)
                return
            except Exception:
                self._log("Arduino desligou-se — a usar o teclado do PC.")
                self._ard.close()
                self._ard = None
                self._ard_state = "nao_procurado"
                self._detect_local_output()
        if self._ard_state == "ok":
            self._ard.key(key, hold)
        else:
            key_down(SCAN[key])
            time.sleep(hold)
            key_up(SCAN[key])

    def _local_move(self, dx, dy):
        if self._ard_state == "ok":
            try:
                self._ard.move(dx, dy)
                return
            except Exception:
                pass
        mouse_move(dx, dy)

    def _local_pad(self):
        if self._pad is None:
            import vgamepad as vg

            self._pad = vg.VX360Gamepad()
            self._log("Comando virtual Xbox criado (ViGEm).")
        return self._pad

    def _run(self):
        remoto = self.destino_var.get() == "Remoto"
        try:
            if remoto:
                self._remote_cmd({"cmd": "ping"})
                self._log("Ligado ao destino remoto. Sessão iniciada.")
            else:
                self._log("Sessão iniciada. NÃO feches esta janela.")
            while self.running:
                modo = self.mode_var.get()
                if modo == "Comando":
                    import math

                    ang = random.uniform(0, 2 * math.pi)
                    mag = random.uniform(0.25, 0.6)
                    lx = math.cos(ang) * mag
                    ly = math.sin(ang) * mag
                    hold = random.uniform(0.3, 1.2)
                    if remoto:
                        self._remote_cmd(
                            {"cmd": "pad", "lx": lx, "ly": ly, "hold": hold}
                        )
                    else:
                        try:
                            pad = self._local_pad()
                        except Exception as e:
                            raise RuntimeError(
                                f"Comando virtual indisponível: {e}. "
                                "Instala o driver ViGEmBus_Setup.exe."
                            )
                        pad.left_joystick_float(lx, ly)
                        pad.update()
                        time.sleep(hold)
                        pad.left_joystick_float(0, 0)
                        pad.update()
                    self._log(
                        f"[{'Remoto' if remoto else 'Local'}] Comando: analógica "
                        f"({lx:+.2f}, {ly:+.2f}) {hold:.2f}s"
                    )
                else:
                    key = random.choice(list(SCAN.keys()))
                    hold = random.uniform(0.15, 0.5)
                    if remoto:
                        self._remote_cmd({"cmd": "key", "k": key, "hold": hold})
                    else:
                        self._local_key(key, hold)
                    self._log(
                        f"[{'Remoto' if remoto else 'Local'}] Tecla {key.upper()} ({hold:.2f}s)"
                    )

                    if modo in ("Rato", "Ambos"):
                        dx = random.randint(-60, 60)
                        dy = random.randint(-25, 25)
                        if remoto:
                            self._remote_cmd({"cmd": "move", "dx": dx, "dy": dy})
                        else:
                            self._local_move(dx, dy)
                        self._log(
                            f"[{'Remoto' if remoto else 'Local'}] Rato ({dx:+d}, {dy:+d})"
                        )

                intervalo = self.interval_var.get()
                fim = time.time() + intervalo
                while self.running and time.time() < fim:
                    time.sleep(0.1)
            self._log("Sessão parada.")
        except Exception as e:
            self._log(f"Erro: {e}")
            self.after(0, self.stop)

    def _hotkey_loop(self):
        if not user32.RegisterHotKey(None, HOTKEY_ID, 0, VK_F8):
            return
        msg = ctypes.wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
            if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                self.after(0, self.toggle)
        user32.UnregisterHotKey(None, HOTKEY_ID)

    def _auto_rescan(self):
        if (self.auto or self._resume_when_found) and not self.running:
            self.refresh_processes()
        self.after(5000 if self._resume_when_found else 30000, self._auto_rescan)

    def _log(self, msg):
        ts = datetime.datetime.now().strftime("%H:%M:%S")

        def append():
            self.log_box.configure(state="normal")
            self.log_box.insert("end", f"[{ts}] {msg}\n")
            self.log_box.see("end")
            self.log_box.configure(state="disabled")

        self.after(0, append)

    def _on_close(self):
        self.running = False
        self.video_on = False
        self._remote_disconnect()
        try:
            if self.video_sock:
                self.video_sock.close()
        except Exception:
            pass
        self.destroy()


if __name__ == "__main__":
    app = App()
    app.mainloop()
