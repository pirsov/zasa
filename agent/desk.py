"""Персонаж на рабочем столе: ходит по экрану и отдаёт фразу Джарвису.

Окно без рамки, поверх остальных. Клик открывает строку. Свой GIF, в том
числе персонаж из DesktopDance, передаётся ключом --gif.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import threading
from dataclasses import dataclass

_CLEAR = "#ff00ff"
_WIDTH = 200
_HEIGHT = 220


@dataclass
class Walker:
    """Шаг вдоль нижнего края экрана. В состоянии think и talk стоит."""

    x: int
    y: int
    screen_w: int
    width: int = _WIDTH
    direction: int = 1
    state: str = "walk"
    speed: int = 6
    frame: int = 0

    def step(self) -> None:
        self.frame += 1
        if self.state != "walk":
            return
        self.x += self.speed * self.direction
        if self.x <= 0:
            self.x = 0
            self.direction = 1
        limit = max(0, self.screen_w - self.width)
        if self.x >= limit:
            self.x = limit
            self.direction = -1


def last_reply(facts: list[str]) -> str:
    for fact in reversed(facts):
        if fact.startswith("Агент: "):
            return fact.removeprefix("Агент: ").strip()
    return ""


def run_jarvis(task: str) -> str:
    from agent.orchestrator import Orchestrator

    try:
        orchestrator = Orchestrator()
        asyncio.run(orchestrator.run(task))
    except Exception as exc:
        return str(exc) or "Не получилось."
    return last_reply(orchestrator.memory.load()) or "Готово."


def parse_args(argv: list[str]) -> str | None:
    parser = argparse.ArgumentParser(prog="python -m agent.desk")
    parser.add_argument("--gif", default=None, help="GIF персонажа, например из DesktopDance")
    args = parser.parse_args(argv)
    return args.gif


class Pet:
    """Маленькое окно с фигурой. run_task получает фразу и возвращает ответ."""

    def __init__(
        self,
        run_task,
        gif_path: str | None = None,
        screen_size: tuple[int, int] | None = None,
    ) -> None:
        import tkinter as tk

        self._tk = tk
        self.run_task = run_task
        self.root = tk.Tk()
        self.root.title("Джарвис")
        self.root.overrideredirect(True)
        self.root.configure(bg=_CLEAR)
        try:
            self.root.wm_attributes("-topmost", True)
        except tk.TclError:
            pass
        try:
            self.root.wm_attributes("-transparentcolor", _CLEAR)
        except tk.TclError:
            pass
        try:
            self.root.attributes("-toolwindow", True)
        except tk.TclError:
            pass
        screen_w = screen_size[0] if screen_size else self.root.winfo_screenwidth()
        screen_h = screen_size[1] if screen_size else self.root.winfo_screenheight()
        self.walker = Walker(x=40, y=max(0, screen_h - _HEIGHT - 72), screen_w=screen_w)
        self.canvas = tk.Canvas(
            self.root,
            width=_WIDTH,
            height=_HEIGHT,
            bg=_CLEAR,
            highlightthickness=0,
            bd=0,
        )
        self.canvas.pack()
        self.bubble = ""
        self._frames: list = []
        self._chat = None
        self._entry = None
        self._reply_var = None
        if gif_path:
            self._frames = _gif_frames(tk, gif_path)
        self.canvas.bind("<ButtonPress-1>", self._press)
        self.canvas.bind("<B1-Motion>", self._drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_click)
        self.canvas.bind("<Button-3>", lambda _event: self.close())
        self._press_at: tuple[int, int] | None = None
        self._moved = False
        self._place()
        self._draw()

    def tick(self) -> None:
        self.walker.step()
        self._place()
        self._draw()

    def submit(self, text: str) -> None:
        phrase = text.strip()
        if not phrase or self.walker.state == "think":
            return
        self.walker.state = "think"
        self.bubble = "Думаю..."
        self._draw()
        if self._reply_var is not None:
            self._reply_var.set(self.bubble)
        threading.Thread(target=self._work, args=(phrase,), daemon=True).start()

    def close(self) -> None:
        if self._chat is not None:
            self._chat.destroy()
            self._chat = None
        self.root.destroy()

    def mainloop(self) -> None:
        self.root.after(50, self._loop)
        self.root.mainloop()

    def _loop(self) -> None:
        if not self.root.winfo_exists():
            return
        self.tick()
        self.root.after(50, self._loop)

    def _work(self, phrase: str) -> None:
        try:
            reply = self.run_task(phrase)
        except Exception as exc:
            reply = str(exc) or "Не получилось."
        self.root.after(0, lambda: self._finish(reply))

    def _finish(self, reply: str) -> None:
        self.bubble = reply
        self.walker.state = "talk"
        if self._reply_var is not None:
            self._reply_var.set(reply)
        self._draw()

    def _place(self) -> None:
        self.root.geometry(f"{_WIDTH}x{_HEIGHT}+{self.walker.x}+{self.walker.y}")

    def _press(self, event) -> None:
        self._press_at = (event.x_root, event.y_root)
        self._moved = False

    def _drag(self, event) -> None:
        if self._press_at is None:
            return
        dx = event.x_root - self._press_at[0]
        dy = event.y_root - self._press_at[1]
        if abs(dx) + abs(dy) < 6:
            return
        self._moved = True
        self.walker.state = "talk"
        self.walker.x = max(0, min(self.walker.screen_w - self.walker.width, self.walker.x + dx))
        self.walker.y = max(0, self.walker.y + dy)
        self._press_at = (event.x_root, event.y_root)
        self._place()

    def _on_click(self, _event) -> None:
        if self._moved:
            self._moved = False
            self.walker.state = "walk"
            return
        self._open_chat()

    def _open_chat(self) -> None:
        self.walker.state = "talk"
        if self._chat is not None and self._chat.winfo_exists():
            self._chat.lift()
            self._entry.focus_set()
            return
        chat = self._tk.Toplevel(self.root)
        chat.title("Джарвис")
        chat.configure(bg="#1c2430")
        chat.geometry(f"320x150+{self.walker.x}+{max(0, self.walker.y - 160)}")
        try:
            chat.wm_attributes("-topmost", True)
        except self._tk.TclError:
            pass
        reply = self._tk.StringVar(value=self.bubble or "Слушаю.")
        self._reply_var = reply
        label = self._tk.Label(
            chat,
            textvariable=reply,
            bg="#1c2430",
            fg="#f4f1ea",
            wraplength=300,
            justify="left",
            anchor="w",
        )
        label.pack(fill="both", expand=True, padx=10, pady=(10, 4))
        entry = self._tk.Entry(chat, bg="#f4f1ea", fg="#1c2430", insertbackground="#1c2430")
        entry.pack(fill="x", padx=10, pady=(0, 10))
        entry.bind("<Return>", lambda _event: self._send(entry))
        entry.focus_set()
        self._chat = chat
        self._entry = entry

    def _send(self, entry) -> None:
        phrase = entry.get()
        entry.delete(0, "end")
        self.submit(phrase)

    def _draw(self) -> None:
        canvas = self.canvas
        canvas.delete("fig")
        if self._frames:
            frame = self._frames[self.walker.frame % len(self._frames)]
            canvas.create_image(_WIDTH // 2, _HEIGHT - 8, image=frame, anchor="s", tags="fig")
        else:
            _draw_person(canvas, self.walker.frame, self.walker.direction, self.walker.state)
        if self.bubble:
            _draw_bubble(canvas, self.bubble)


def _draw_person(canvas, frame: int, direction: int, state: str) -> None:
    cx = _WIDTH // 2
    ground = _HEIGHT - 10
    step = 12 if (frame // 3) % 2 == 0 else -12
    if state != "walk":
        step = 0
    canvas.create_oval(cx - 26, ground - 6, cx + 26, ground + 4, fill="#2a241c", outline="", tags="fig")
    canvas.create_line(cx - 2, ground - 52, cx - 14 + step, ground - 6, width=5, fill="#1a1a1a", capstyle="round", tags="fig")
    canvas.create_line(cx + 2, ground - 52, cx + 14 - step, ground - 6, width=5, fill="#1a1a1a", capstyle="round", tags="fig")
    canvas.create_polygon(
        cx - 18, ground - 54,
        cx + 18, ground - 54,
        cx + 14, ground - 96,
        cx - 14, ground - 96,
        fill="#243044",
        outline="",
        tags="fig",
    )
    canvas.create_line(
        cx,
        ground - 78,
        cx + 22 * direction,
        ground - 60,
        width=4,
        fill="#243044",
        capstyle="round",
        tags="fig",
    )
    canvas.create_oval(cx - 16, ground - 128, cx + 16, ground - 96, fill="#f0c9a0", outline="", tags="fig")
    visor = "#3ddc97" if state != "think" else "#f0c14a"
    canvas.create_rectangle(cx - 11, ground - 118, cx + 11, ground - 108, fill=visor, outline="", tags="fig")


def _draw_bubble(canvas, text: str) -> None:
    shown = text if len(text) <= 42 else text[:41] + "…"
    canvas.create_rectangle(8, 8, _WIDTH - 8, 62, fill="#1c2430", outline="", tags="fig")
    canvas.create_text(16, 14, text=shown, fill="#f4f1ea", anchor="nw", width=_WIDTH - 32, tags="fig")


def _gif_frames(tk, path: str) -> list:
    frames = []
    index = 0
    while index < 48:
        try:
            frames.append(tk.PhotoImage(file=path, format=f"gif -index {index}"))
        except tk.TclError:
            break
        index += 1
    if frames:
        return frames
    return [tk.PhotoImage(file=path)]


def main(argv: list[str] | None = None) -> None:
    gif = parse_args(sys.argv[1:] if argv is None else argv)
    Pet(run_task=run_jarvis, gif_path=gif).mainloop()


if __name__ == "__main__":
    main()
