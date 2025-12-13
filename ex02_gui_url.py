import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import json
import urllib.request
import urllib.error

# cfg
DEFAULT_BASE_URL = "http://localhost:1234/v1"
DEFAULT_MODEL = ""  # zostaw puste -> wybierzesz z listy /models
SYSTEM_PROMPT = "Jesteś pomocnym asystentem."

messages = [{"role": "system", "content": SYSTEM_PROMPT}]

root = None
chat_box = None
base_url_var = None
api_key_var = None
input_var = None
input_entry = None
send_btn = None
stop_btn = None
clear_btn = None
status_var = None

model_var = None
model_combo = None
refresh_models_btn = None

stop_event = threading.Event()
current_response = None  # uchwyt do aktywnego połączenia (do przerwania)

def _make_request(url: str, method: str = "GET", headers=None, data: bytes | None = None):
    req = urllib.request.Request(url, data=data, method=method)
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    return req

def _auth_headers(api_key: str) -> dict:
    api_key = (api_key or "").strip()
    if not api_key:
        return {}
    return {"Authorization": f"Bearer {api_key}"}


def lmstudio_get_models(base_url: str, api_key: str) -> list[str]:
    base_url = base_url.rstrip("/")
    url = f"{base_url}/models"

    headers = {"Accept": "application/json"}
    headers.update(_auth_headers(api_key))

    req = _make_request(url, "GET", headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        obj = json.loads(resp.read().decode("utf-8"))
        data = obj.get("data", [])
        models = [m.get("id", "") for m in data if m.get("id")]
        models.sort()
        return models


def lmstudio_chat_stream(base_url: str, api_key: str, model: str, msgs: list,
                         temperature: float = 0.7, max_tokens: int = 700):

    base_url = base_url.rstrip("/")
    url = f"{base_url}/chat/completions"

    payload = {
        "model": model,
        "messages": msgs,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True,
    }

    headers = {
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }
    headers.update(_auth_headers(api_key))

    data = json.dumps(payload).encode("utf-8")
    req = _make_request(url, "POST", headers=headers, data=data)

    global current_response
    current_response = urllib.request.urlopen(req, timeout=300)

    try:
        while True:
            if stop_event.is_set():
                break

            line = current_response.readline()
            if not line:
                break

            line = line.decode("utf-8", errors="replace").strip()
            if not line:
                continue

            if not line.startswith("data:"):
                continue

            data_str = line[len("data:"):].strip()
            if data_str == "[DONE]":
                break

            try:
                chunk = json.loads(data_str)
                choices = chunk.get("choices", [])
                if not choices:
                    continue
                delta = choices[0].get("delta", {})
                piece = delta.get("content")
                if piece:
                    yield piece
            except json.JSONDecodeError:
                # czasem mogą wpaść nietypowe linie; ignorujemy
                continue
    finally:
        try:
            current_response.close()
        except Exception:
            pass
        current_response = None


def append_chat(who: str, text: str) -> None:
    chat_box.configure(state="normal")
    chat_box.insert(tk.END, f"{who}:\n{text}\n\n")
    chat_box.configure(state="disabled")
    chat_box.see(tk.END)


def append_stream_piece(piece: str) -> None:
    chat_box.configure(state="normal")
    chat_box.insert(tk.END, piece)
    chat_box.configure(state="disabled")
    chat_box.see(tk.END)


def set_busy(busy: bool) -> None:
    state_send = "disabled" if busy else "normal"
    state_stop = "normal" if busy else "disabled"

    send_btn.configure(state=state_send)
    input_entry.configure(state=state_send)
    clear_btn.configure(state=state_send)
    refresh_models_btn.configure(state=state_send)
    model_combo.configure(state=("disabled" if busy else "readonly"))

    stop_btn.configure(state=state_stop)


def safe_show_error(title: str, err: Exception) -> None:
    messagebox.showerror(title, str(err))


def on_clear() -> None:
    global messages
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    chat_box.configure(state="normal")
    chat_box.delete("1.0", tk.END)
    chat_box.configure(state="disabled")
    status_var.set("Wyczyszczono historię.")


def on_stop() -> None:
    stop_event.set()
    status_var.set("Zatrzymywanie…")
    global current_response
    try:
        if current_response is not None:
            current_response.close()
    except Exception:
        pass


def on_send(event=None) -> None:
    text = (input_var.get() or "").strip()
    if not text:
        return

    # model
    model = (model_var.get() or "").strip()
    if not model:
        messagebox.showwarning("Brak modelu", "Wybierz model (Odśwież listę modeli, jeśli pusta).")
        return

    input_var.set("")
    append_chat("Ty", text)
    messages.append({"role": "user", "content": text})

    status_var.set("Generowanie (stream)…")
    stop_event.clear()
    set_busy(True)

    chat_box.configure(state="normal")
    chat_box.insert(tk.END, "AI:\n")
    chat_box.configure(state="disabled")
    chat_box.see(tk.END)

    threading.Thread(target=do_stream_worker, daemon=True).start()


def do_stream_worker() -> None:
    model = (model_var.get() or "").strip()
    base_url = (base_url_var.get() or "").strip()
    api_key = (api_key_var.get() or "").strip()

    full_reply_parts = []

    try:
        for piece in lmstudio_chat_stream(
            base_url=base_url,
            api_key=api_key,
            model=model,
            msgs=messages,
            temperature=0.7,
            max_tokens=700
        ):
            if stop_event.is_set():
                break
            full_reply_parts.append(piece)
            root.after(0, lambda p=piece: append_stream_piece(p))

        # zakończ estetycznie blok AI
        root.after(0, lambda: append_stream_piece("\n\n"))

        final_text = "".join(full_reply_parts).strip()
        if final_text:
            messages.append({"role": "assistant", "content": final_text})

        if stop_event.is_set():
            root.after(0, lambda: status_var.set("Zatrzymano."))
        else:
            root.after(0, lambda: status_var.set("Gotowe."))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        root.after(0, lambda: status_var.set("Błąd."))
        root.after(0, lambda: safe_show_error("HTTPError", RuntimeError(f"HTTPError {e.code}: {body}")))
    except urllib.error.URLError as e:
        root.after(0, lambda: status_var.set("Błąd połączenia."))
        root.after(0, lambda: safe_show_error(
            "Błąd połączenia",
            RuntimeError(
                f"Nie mogę połączyć się z {base_url}/chat/completions.\n"
                f"Sprawdź LM Studio -> Local Server. ({e})"
            )
        ))
    except Exception as e:
        root.after(0, lambda: status_var.set("Błąd."))
        root.after(0, lambda: safe_show_error("Błąd", e))
    finally:
        root.after(0, lambda: set_busy(False))
        stop_event.clear()


def on_refresh_models() -> None:
    status_var.set("Pobieranie listy modeli…")
    refresh_models_btn.configure(state="disabled")
    threading.Thread(target=refresh_models_worker, daemon=True).start()


def refresh_models_worker() -> None:
    base_url = (base_url_var.get() or "").strip()
    api_key = (api_key_var.get() or "").strip()

    try:
        models = lmstudio_get_models(base_url, api_key)
        root.after(0, lambda: apply_models(models))
        root.after(0, lambda: status_var.set("Lista modeli zaktualizowana."))
    except Exception as e:
        root.after(0, lambda: status_var.set("Nie udało się pobrać modeli."))
        root.after(0, lambda: safe_show_error("Modele", e))
    finally:
        root.after(0, lambda: refresh_models_btn.configure(state="normal"))


def apply_models(models: list[str]) -> None:
    model_combo["values"] = models
    if models:
        # jeśli aktualnie nie wybrano modelu lub jest niepoprawny -> ustaw pierwszy
        current = (model_var.get() or "").strip()
        if not current or current not in models:
            model_var.set(models[0])


def build_ui() -> None:
    global chat_box, base_url_var, api_key_var, input_var, input_entry
    global send_btn, stop_btn, clear_btn, status_var
    global model_var, model_combo, refresh_models_btn

    root.title("LM Studio Chat")
    root.geometry("900x620")

    top = ttk.Frame(root, padding=10)
    top.pack(fill="x")

    ttk.Label(top, text="Base URL:").grid(row=0, column=0, sticky="w")
    base_url_var = tk.StringVar(value=DEFAULT_BASE_URL)
    ttk.Entry(top, textvariable=base_url_var, width=40).grid(row=0, column=1, sticky="we", padx=5)

    ttk.Label(top, text="API key (opcjonalnie):").grid(row=0, column=2, sticky="w", padx=(10, 0))
    api_key_var = tk.StringVar(value="")
    ttk.Entry(top, textvariable=api_key_var, width=25, show="•").grid(row=0, column=3, sticky="we", padx=5)

    ttk.Label(top, text="Model:").grid(row=1, column=0, sticky="w", pady=(8, 0))
    model_var = tk.StringVar(value=DEFAULT_MODEL)
    model_combo = ttk.Combobox(top, textvariable=model_var, values=[], state="readonly", width=42)
    model_combo.grid(row=1, column=1, sticky="we", padx=5, pady=(8, 0))

    refresh_models_btn = ttk.Button(top, text="Odśwież modele", command=on_refresh_models)
    refresh_models_btn.grid(row=1, column=2, sticky="w", padx=(10, 0), pady=(8, 0))

    top.columnconfigure(1, weight=1)

    mid = ttk.Frame(root, padding=(10, 0, 10, 10))
    mid.pack(fill="both", expand=True)

    chat_box = scrolledtext.ScrolledText(mid, wrap=tk.WORD, state="disabled", font=("Segoe UI", 10))
    chat_box.pack(fill="both", expand=True)

    bottom = ttk.Frame(root, padding=10)
    bottom.pack(fill="x")

    input_var = tk.StringVar()
    input_entry = ttk.Entry(bottom, textvariable=input_var)
    input_entry.pack(side="left", fill="x", expand=True)
    input_entry.bind("<Return>", on_send)

    send_btn = ttk.Button(bottom, text="Wyślij", command=on_send)
    send_btn.pack(side="left", padx=(10, 0))

    stop_btn = ttk.Button(bottom, text="Stop", command=on_stop, state="disabled")
    stop_btn.pack(side="left", padx=(10, 0))

    clear_btn = ttk.Button(bottom, text="Wyczyść", command=on_clear)
    clear_btn.pack(side="left", padx=(10, 0))

    status_var = tk.StringVar(value="Gotowe. Kliknij „Odśwież modele”, potem wyślij wiadomość.")
    ttk.Label(root, textvariable=status_var, anchor="w", padding=(10, 0, 10, 10)).pack(fill="x")

    input_entry.focus_set()


def main() -> None:
    global root
    root = tk.Tk()
    build_ui()
    root.mainloop()


if __name__ == "__main__":
    main()