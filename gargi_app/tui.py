"""GARGI Terminal UI - Textual-powered TUI."""

import time
import random
import asyncio

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Header, Footer, Static, Input, Button

from rich.align import Align
from rich.console import Group
from rich.markdown import Markdown
from rich.text import Text

from .ascii_art import (
    BOOT_BANNER, render_face, SELECTABLE_MOODS, FACE_WIDTH, FACE_HEIGHT,
)
from .persona import (
    MOODS, get_greeting, get_current_vibe, get_random_hobby, get_random_starter,
)
from .agent import (
    GargiAgent, MODELS, get_api_key, save_api_key, get_config, save_config,
    get_saved_model, get_user_name, save_user_name,
)
from .voice import Voice

# get_current_vibe() must never hand back a mood the face module can't draw,
# otherwise render_face silently falls back to neutral and the mood system
# looks like it works while doing nothing.
_UNDRAWABLE = set(MOODS) - set(SELECTABLE_MOODS)
if _UNDRAWABLE:
    raise RuntimeError(f"moods with no face frame: {sorted(_UNDRAWABLE)}")

PINK = "white"
CYAN = "white"
DIM = "dim"
GREEN = "white"

FACE_PANEL_WIDTH = FACE_WIDTH + 6

IDLE_LINES = [
    "yo you still there?",
    "it got quiet. you good?",
    "ok i'm bored. entertain me",
    "random: what are you working on rn?",
    "i just thought of something wild. wanna hear it?",
    "psst. still awake?",
]


class APIKeyScreen(ModalScreen):
    DEFAULT_CSS = """
    APIKeyScreen { align: center middle; background: black; }
    #dialog { width: 68; height: auto; padding: 1 2; background: black; border: solid gray; }
    #dialog Input { margin: 1 0; background: black; border: solid gray; }
    #dialog Input:focus { border: solid white; }
    #btnrow { height: auto; align-horizontal: center; }
    #btnrow Button { margin: 0 1; }
    """

    def compose(self) -> ComposeResult:
        with Container(id="dialog"):
            yield Static(Text.from_markup(
                f"[bold {PINK}]hey, i need a brain[/]\n\n"
                "grab a free NVIDIA NIM key (no card needed):\n"
                f"  [bold {CYAN}]build.nvidia.com[/]\n\n"
                f"[{DIM}]paste it below[/]"
            ))
            yield Input(placeholder="nvapi-...", password=True, id="key")
            with Horizontal(id="btnrow"):
                yield Button("save & go", variant="primary", id="save")
                yield Button("skip", id="skip")

    def on_mount(self):
        self.query_one("#key", Input).focus()

    @on(Button.Pressed, "#save")
    @on(Input.Submitted, "#key")
    def _save(self):
        key = self.query_one("#key", Input).value.strip()
        if key.startswith("nvapi-") and len(key) > 20:
            save_api_key(key)
            self.dismiss(key)
        else:
            self.notify("key should start with 'nvapi-'", severity="error")

    @on(Button.Pressed, "#skip")
    def _skip(self):
        self.dismiss("__skip__")


class GargiApp(App):
    TITLE = "GARGI"
    SUB_TITLE = "Generally A Really Good Interface"

    CSS = f"""
    Screen {{ background: black; }}
    Header {{ background: black; color: white; }}
    Footer {{ background: black; }}

    #main {{ layout: horizontal; height: 1fr; }}
    #left {{ width: {FACE_PANEL_WIDTH}; height: 1fr; background: black; padding: 1 1 0 1; border-right: solid gray; }}
    #face {{ height: auto; }}
    #stats {{ height: auto; padding: 1 1 0 2; }}
    #stats Static {{ height: 1; }}

    #right {{ width: 1fr; height: 1fr; }}
    #chat {{
        height: 1fr; padding: 1 2; background: black;
        scrollbar-color: gray; scrollbar-background: black;
    }}
    .msg {{ width: 1fr; height: auto; padding: 0 0 0 1; margin-bottom: 1; }}
    .msg-user {{ border-left: solid white; }}
    .msg-gargi {{ border-left: solid gray; }}
    .msg-sys {{ border-left: solid gray; color: gray; }}

    #hint {{ height: 1; padding: 0 2; background: black; color: gray; }}
    #inputrow {{ height: auto; padding: 1 2; background: black; }}
    #msg {{ width: 1fr; background: black; color: white; border: solid gray; }}
    #msg:focus {{ border: solid white; }}
    #send {{ margin-left: 1; min-width: 10; background: white; color: black; border: none; }}
    """

    BINDINGS = [
        Binding("ctrl+q", "quit", "quit"),
        Binding("ctrl+r", "reset", "reset"),
        Binding("ctrl+t", "voice", "voice"),
        Binding("ctrl+s", "stop", "stop"),
        Binding("ctrl+f", "cycle_face", "face"),
        Binding("escape", "focus_input", "input", show=False),
    ]

    def __init__(self):
        super().__init__()
        self.agent = None
        self.voice = Voice()
        self._mood = get_current_vibe()
        self._hobby = get_random_hobby()
        self._phase = 0
        self._blink_until = 0.0
        self._speaking = False
        self._thinking = False
        self._last_face_key = None
        self._last_activity = time.monotonic()
        self._face_widget = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="main"):
            with Vertical(id="left"):
                yield Static(id="face")
                with Vertical(id="stats"):
                    yield Static(id="s-mood")
                    yield Static(id="s-hobby")
                    yield Static(id="s-model")
                    yield Static(id="s-voice")
                    yield Static(id="s-status")
            with Vertical(id="right"):
                yield VerticalScroll(id="chat")
                yield Static(Text.from_markup(f"[{DIM}]/help  ·  ctrl+Q quit[/]"), id="hint")
                with Horizontal(id="inputrow"):
                    yield Input(placeholder="talk to GARGI...", id="msg")
                    yield Button("send", variant="primary", id="send")
        yield Footer()

    def on_mount(self):
        self._face_widget = self.query_one("#face", Static)
        self.voice.enabled = bool(get_config().get("voice", False)) and self.voice.available
        self._paint_face(force=True)
        self._paint_stats()
        self.set_interval(0.28, self._tick_face)
        self.set_interval(20.0, self._idle_check)
        self.set_interval(120.0, self._refresh_mood)
        self.query_one("#msg", Input).focus()
        self._boot()

    @work
    async def _boot(self):
        api_key = get_api_key()
        if not api_key:
            try:
                result = await self.push_screen_wait(APIKeyScreen())
            except Exception:
                result = None
            if result and result != "__skip__":
                api_key = result

        if not api_key:
            self._sys("offline mode. type /setup when ready.")
            self._bubble_gargi(get_greeting())
            return

        self._sys("waking up...")
        agent = GargiAgent(api_key, get_saved_model(), get_user_name())
        ok, msg = await asyncio.to_thread(agent.validate_key)

        if ok:
            self.agent = agent
            self._sys(msg)
            self._paint_stats()
            greeting = get_greeting()
            self._bubble_gargi(greeting)
            self._bubble_gargi(f"currently obsessed with *{self._hobby}* btw")
            self._start_talking(greeting)
        else:
            self._sys(msg)
            self._bubble_gargi("couldn't connect my brain. type /setup")

    def _paint_face(self, blink=False, force=False):
        if self._face_widget is None:
            return

        key = (self._mood, self._thinking, self._speaking, blink, self._phase if (self._speaking or blink) else 0)
        if not force and key == self._last_face_key:
            return
        self._last_face_key = key

        face = render_face(mood=self._mood, blink=blink, speaking=self._speaking, phase=self._phase, thinking=self._thinking)

        if self._thinking:
            title = "GARGI | thinking"
        elif self._speaking:
            title = "GARGI | speaking"
        else:
            title = f"GARGI | {self._mood}"

        self._face_widget.update(Group(Text(title, style="bold"), Align.center(Text(face))))

    def _tick_face(self):
        self._phase += 1
        now = time.monotonic()
        blink = False
        if not self._thinking and not self._speaking:
            if now < self._blink_until:
                blink = True
            elif random.random() < 0.08:
                self._blink_until = now + 0.28
                blink = True
        self._paint_face(blink=blink)

    def _refresh_mood(self):
        new_mood = get_current_vibe()
        if new_mood != self._mood:
            self._mood = new_mood
            self._hobby = get_random_hobby()
            self._paint_stats()
            self._paint_face(force=True)

    def _paint_stats(self):
        model = self.agent.model if self.agent else "not connected"
        model_short = model.split("/")[-1]

        if not self.voice.available:
            vtext = f"[{DIM}]voice unavailable[/]"
        elif self.voice.enabled:
            vtext = f"voice [bold {GREEN}]ON[/]"
        else:
            vtext = f"voice [{DIM}]off[/]"

        self.query_one("#s-mood", Static).update(Text.from_markup(f"vibe    {self._mood}"))
        self.query_one("#s-hobby", Static).update(Text.from_markup(f"into    [italic {CYAN}]{self._hobby}[/]"))
        self.query_one("#s-model", Static).update(Text.from_markup(f"brain   [{DIM}]{model_short}[/]"))
        self.query_one("#s-voice", Static).update(Text.from_markup(vtext))
        self._paint_status()

    def _paint_status(self):
        if self._thinking:
            txt = f"status  [bold {CYAN}]thinking[/]"
        elif self._speaking:
            txt = f"status  [bold {PINK}]talking[/]"
        elif self.agent:
            turns = self.agent.turn_count
            txt = f"status  [{GREEN}]online[/] [{DIM}]{turns} turns[/]"
        else:
            txt = f"status  [{DIM}]offline[/]"
        try:
            self.query_one("#s-status", Static).update(Text.from_markup(txt))
        except Exception:
            pass

    def _mount(self, widget: Static) -> Static:
        chat = self.query_one("#chat", VerticalScroll)
        chat.mount(widget)
        chat.scroll_end(animate=False)
        return widget

    def _sys(self, markup: str):
        self._mount(Static(Text.from_markup(markup), classes="msg msg-sys"))

    def _bubble_user(self, text: str):
        body = Group(Text("YOU", style=f"bold {CYAN}"), Text(text))
        self._mount(Static(body, classes="msg msg-user"))

    def _bubble_gargi(self, text: str) -> Static:
        body = Group(Text("GARGI", style=f"bold {PINK}"), Markdown(text))
        return self._mount(Static(body, classes="msg msg-gargi"))

    def _new_stream_bubble(self) -> Static:
        body = Group(Text("GARGI", style=f"bold {PINK}"), Text("|", style=DIM))
        return self._mount(Static(body, classes="msg msg-gargi"))

    # Roughly how long TTS takes per character, measured against SAPI at
    # rate 2. Only used to decide when to stop the mouth animation.
    _SECONDS_PER_CHAR = 0.055
    _SILENT_PULSE = 0.9

    @on(Button.Pressed, "#send")
    @on(Input.Submitted, "#msg")
    def _submit(self):
        field = self.query_one("#msg", Input)
        text = field.value.strip()
        if not text:
            return
        field.value = ""
        self._last_activity = time.monotonic()

        if text.startswith("/"):
            self._command(text)
            return

        self._bubble_user(text)

        if self.agent is None:
            self._bubble_gargi("i'm offline. type **/setup** to connect")
            return
        if self._thinking:
            self._sys("still answering the last one...")
            return

        self.voice.stop()
        self._thinking = True
        self._speaking = False
        self._paint_face(force=True)
        self._paint_status()
        bubble = self._new_stream_bubble()
        self._stream(text, bubble)

    @work(thread=True, group="chat", exclusive=True)
    def _stream(self, text: str, bubble: Static):
        buf = ""
        last_push = 0.0
        try:
            for piece in self.agent.chat_stream(text):
                buf += piece
                now = time.monotonic()
                if now - last_push > 0.06:
                    last_push = now
                    self.call_from_thread(self._push_stream, bubble, buf, False)
        except Exception as exc:
            buf += f"\n\n[!] {exc}"
        finally:
            self.call_from_thread(self._push_stream, bubble, buf, True)

    def _push_stream(self, bubble: Static, buf: str, final: bool):
        label = Text("GARGI", style=f"bold {PINK}")
        if final:
            text = buf.strip() or "nothing came back"
            bubble.update(Group(label, Markdown(text)))
            self._thinking = False
            self._last_activity = time.monotonic()
            self._start_talking(text)
        else:
            bubble.update(Group(label, Text(buf + "|")))
        try:
            self.query_one("#chat", VerticalScroll).scroll_end(animate=False)
        except Exception:
            pass

    def _start_talking(self, text: str):
        """
        Animate the mouth. With voice on the animation tracks the estimated
        speech length; with voice off it is a short pulse, because holding a
        talking face for 20 seconds with no audio just looks broken.
        """
        if self.voice.enabled:
            self.voice.speak(text)
            duration = min(20.0, max(1.6, len(text) * self._SECONDS_PER_CHAR))
        else:
            duration = self._SILENT_PULSE

        self._speaking = True
        self._paint_face(force=True)
        self._paint_status()
        self.set_timer(duration, self._stop_talking)

    def _stop_talking(self):
        if not self._speaking:
            return
        self._speaking = False
        self._paint_face(force=True)
        self._paint_status()

    def _idle_check(self):
        if self.agent is None or self._thinking or self._speaking:
            return
        if time.monotonic() - self._last_activity < 240:
            return
        self._last_activity = time.monotonic()
        line = random.choice(IDLE_LINES + [get_random_starter()])
        self._bubble_gargi(line)
        self._start_talking(line)

    def _command(self, raw: str):
        parts = raw.strip().split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

        if cmd in ("/help", "/h", "/?"):
            self._sys(
                f"[bold {PINK}]commands[/]\n"
                "  /setup    connect API key\n"
                "  /models   list models\n"
                "  /model    switch model\n"
                "  /voice    toggle TTS\n"
                "  /face     lock expression\n"
                "  /name     set your name\n"
                "  /mood     current vibe\n"
                "  /hobby    what i'm into\n"
                "  /starter  pick a topic\n"
                "  /reset    clear memory\n"
                "  /clear    clear screen\n"
                "  /about    version info\n"
                "  /quit     exit"
            )
        elif cmd == "/setup":
            self._do_setup()
        elif cmd == "/models":
            lines = [f"[bold {PINK}]free models[/]"]
            for i, (mid, desc) in enumerate(MODELS, 1):
                lines.append(f"  {i}. {mid}\n     [{DIM}]{desc}[/]")
            self._sys("\n".join(lines))
        elif cmd == "/model":
            if not arg:
                self._sys("usage: /model 2")
                return
            target = arg
            if arg.isdigit() and 1 <= int(arg) <= len(MODELS):
                target = MODELS[int(arg) - 1][0]
            cfg = get_config()
            cfg["model"] = target
            save_config(cfg)
            if self.agent:
                self.agent.model = target
                self._sys(f"switched to {target}")
                self._bubble_gargi("new brain, same me")
            else:
                self._sys(f"saved {target}")
            self._paint_stats()
        elif cmd == "/voice":
            self.action_voice()
        elif cmd == "/face":
            if arg not in SELECTABLE_MOODS:
                self._sys("usage: /face " + " | ".join(SELECTABLE_MOODS))
                return
            self._mood = arg
            self._paint_stats()
            self._paint_face(force=True)
            self._bubble_gargi(f"face: **{arg}**")
        elif cmd == "/name":
            if not arg:
                self._sys(f"you're {get_user_name()}. change: /name Aditi")
                return
            save_user_name(arg)
            if self.agent:
                self.agent.user_name = arg
            self._sys(f"calling you {arg}")
            self._bubble_gargi(f"{arg}. suits you")
        elif cmd == "/mood":
            self._mood = get_current_vibe()
            self._hobby = get_random_hobby()
            self._paint_stats()
            self._paint_face(force=True)
            self._bubble_gargi(f"feeling **{self._mood}**")
        elif cmd == "/hobby":
            self._hobby = get_random_hobby()
            self._paint_stats()
            self._bubble_gargi(f"obsessed with **{self._hobby}**")
        elif cmd == "/starter":
            line = get_random_starter()
            self._bubble_gargi(line)
            self._start_talking(line)
        elif cmd == "/reset":
            self.action_reset()
        elif cmd == "/clear":
            self.query_one("#chat", VerticalScroll).remove_children()
            self._sys("cleared")
        elif cmd in ("/about", "/credits"):
            self._sys(
                f"[bold {PINK}]GARGI v1.2[/]\n"
                f"[{DIM}]by Lakshya (Techiral)[/]\n"
                f"[{DIM}]face: {FACE_WIDTH}x{FACE_HEIGHT}[/]"
            )
        elif cmd in ("/quit", "/exit", "/bye"):
            self.voice.stop()
            self.exit()
        else:
            self._sys(f"unknown: {cmd}. try /help")

    @work
    async def _do_setup(self):
        try:
            result = await self.push_screen_wait(APIKeyScreen())
        except Exception:
            self._sys("run python gargi.py --setup instead")
            return
        if not result or result == "__skip__":
            return
        self._sys("checking key...")
        agent = GargiAgent(result, get_saved_model(), get_user_name())
        ok, msg = await asyncio.to_thread(agent.validate_key)
        if ok:
            self.agent = agent
            self._sys(msg)
            self._paint_stats()
            self._bubble_gargi("connected")
        else:
            self._sys(msg)

    def action_reset(self):
        if self.agent:
            self.agent.reset_conversation()
        self._paint_status()
        self._sys("memory wiped")
        self._bubble_gargi("fresh start")

    def action_voice(self):
        if not self.voice.available:
            self._sys("no TTS engine. install espeak-ng on linux")
            return
        on_now = self.voice.toggle()
        cfg = get_config()
        cfg["voice"] = on_now
        save_config(cfg)
        self._paint_stats()
        if on_now:
            self._sys(f"voice ON ({self.voice.backend_name})")
            self._start_talking("you can hear me now")
        else:
            self.voice.stop()
            self._sys("voice off")

    def action_stop(self):
        self.voice.stop()
        self._stop_talking()
        self._sys("stopped")

    def action_cycle_face(self):
        try:
            idx = SELECTABLE_MOODS.index(self._mood)
        except ValueError:
            idx = -1
        self._mood = SELECTABLE_MOODS[(idx + 1) % len(SELECTABLE_MOODS)]
        self._paint_stats()
        self._paint_face(force=True)

    def action_focus_input(self):
        self.query_one("#msg", Input).focus()

    def on_unmount(self):
        try:
            self.voice.stop()
        except Exception:
            pass


def main():
    print(BOOT_BANNER)
    GargiApp().run()


if __name__ == "__main__":
    main()
