"""Blackjack UI - Handles all display and user interaction.

This module intentionally contains *no networking or game logic*.
`Client` interacts with it through a small, stable API (print_* and get_* methods).

The original project used a console UI; this version keeps the same public methods
but renders them in a Tkinter GUI.
"""

from __future__ import annotations

import queue
import threading
from dataclasses import dataclass
from typing import Any, Callable, Optional


try:
    import tkinter as tk
    from tkinter import ttk
    from tkinter import messagebox
except Exception as e:  # pragma: no cover
    tk = None
    ttk = None
    messagebox = None
    _tk_import_error = e
else:
    _tk_import_error = None


@dataclass
class _SyncCall:
    fn: Callable[[], Any]
    done: threading.Event
    result: Any = None
    error: Optional[BaseException] = None


class BlackjackUI:
    """GUI for Blackjack.

    Important: `client.py` calls into this object from its (blocking) networking loop.
    To keep the window responsive without changing client logic, Tkinter runs in its
    own thread and all UI operations are marshalled onto that thread.
    """

    SUIT_SYMBOLS = {0: "♥", 1: "♦", 2: "♣", 3: "♠"}
    RANK_NAMES = {1: "A", 11: "J", 12: "Q", 13: "K"}

    def __init__(self):
        self._ensure_tk_available()

        self._action_queue: "queue.Queue[Callable[[], None]]" = queue.Queue()
        self._ui_ready = threading.Event()
        self._closed = threading.Event()

        self._root: Optional[Any] = None
        self._round_var: Optional[Any] = None
        self._status_var: Optional[Any] = None
        self._activity_var: Optional[Any] = None
        self._server_var: Optional[Any] = None
        self._advice_var: Optional[Any] = None
        self._result_var: Optional[Any] = None
        self._result_style_var: Optional[Any] = None

        self._stat_rounds_var: Optional[Any] = None
        self._stat_wins_var: Optional[Any] = None
        self._stat_losses_var: Optional[Any] = None
        self._stat_ties_var: Optional[Any] = None
        self._stat_win_rate_var: Optional[Any] = None
        self._stat_hits_var: Optional[Any] = None
        self._stat_stands_var: Optional[Any] = None
        self._cards_container: Optional[Any] = None
        self._dealer_cards_container: Optional[Any] = None
        self._player_cards_container: Optional[Any] = None

        self._hit_btn: Optional[Any] = None
        self._stand_btn: Optional[Any] = None

        self._decision_var: Optional[Any] = None

        # UI-only state to label otherwise-ambiguous cards.
        # Client sometimes calls print_card() with owner="" for hit cards and dealer draws.
        # We infer ownership based on the current phase.
        self._phase: str = "idle"  # idle|deal|player|dealer|done

        self._start_ui_thread()
        self._ui_ready.wait(timeout=5)

        # Keep the user experience consistent with the old version.
        self.print_welcome()

    # -----------------------------
    # Public API used by client.py
    # -----------------------------
    def print_welcome(self):
        self._set_activity("Client started. Listening for server offers on UDP 13122…")
        self._set_status("Waiting for offers…")

    def print_offer_received(self, server_ip, server_name):
        self._run_on_ui(lambda: self._set_var(self._server_var, f"Connected offer: {server_name} @ {server_ip}"))
        self._set_activity(f"Received offer from {server_ip} ('{server_name}')")

    def print_round_header(self, round_num):
        # If the previous round finished, show a nice summary and wait for user
        # confirmation before clearing the table for the next round.
        try:
            self._call_ui_sync(self._between_rounds_pause_if_needed)
        except Exception:
            # If UI is closing or modal fails, don't block the client.
            pass

        def _do():
            self._phase = "deal"
            self._set_var(self._round_var, f"Round {round_num}")
            self._set_var(self._status_var, "Dealing cards…")
            self._set_var(self._advice_var, "")
            self._set_var(self._result_var, "")
            self._set_var(self._result_style_var, "neutral")
            self._clear_cards()
        self._run_on_ui(_do)
        self._set_activity(f"Starting round {round_num}")

    def print_waiting_for_cards(self):
        def _do():
            self._phase = "deal"
            self._set_var(self._status_var, "Waiting for cards…")
        self._run_on_ui(_do)
        self._set_activity("Waiting for cards…")

    def print_card(self, rank, suit, owner=""):
        rank_str = self.RANK_NAMES.get(rank, str(rank))
        suit_symbol = self.SUIT_SYMBOLS.get(suit, "?")
        is_red = suit in (0, 1)

        if not owner:
            if self._phase == "player":
                owner = "Player"
            elif self._phase == "dealer":
                owner = "Dealer"
            else:
                owner = "Card"

        def _do():
            self._add_card_widget(owner=owner or "Card", rank=rank_str, suit=suit_symbol, is_red=is_red)
            if owner == "Player":
                self._set_var(self._status_var, "Your move")
        self._run_on_ui(_do)
        self._set_activity(f"{owner}: {rank_str}{suit_symbol}")

    def print_advice(self, advice):
        advice = (advice or "").strip().title()
        self._run_on_ui(lambda: self._set_var(self._advice_var, f"Advisor suggestion: {advice}"))
        self._set_activity(f"Advisor suggests: {advice}")

    def print_standing(self):
        def _do():
            self._phase = "dealer"
            self._set_var(self._status_var, "Standing… Watching dealer")
        self._run_on_ui(_do)
        self._set_activity("Standing… Watching dealer")

    def print_result(self, result_code):
        def _do():
            self._phase = "done"
            text, style_key = self._result_text(result_code)
            self._set_var(self._status_var, "Round finished")
            self._set_var(self._result_var, text)
            self._set_var(self._result_style_var, style_key)
            self._set_decision_buttons_enabled(False)

        self._run_on_ui(_do)
        text, _ = self._result_text(result_code)
        self._set_activity(text)

    def print_statistics(self, stats):
        rounds_played = stats.get("rounds_played", 0)
        wins = stats.get("wins", 0)
        losses = stats.get("losses", 0)
        ties = stats.get("ties", 0)
        hits = stats.get("hits", 0)
        stands = stats.get("stands", 0)
        win_rate = (wins / rounds_played) if rounds_played else 0.0

        def _do():
            self._set_var(self._stat_rounds_var, str(rounds_played))
            self._set_var(self._stat_wins_var, str(wins))
            self._set_var(self._stat_losses_var, str(losses))
            self._set_var(self._stat_ties_var, str(ties))
            self._set_var(self._stat_win_rate_var, f"{win_rate:.2%}")
            self._set_var(self._stat_hits_var, str(hits))
            self._set_var(self._stat_stands_var, str(stands))
        self._run_on_ui(_do)
        self._set_activity("Statistics updated")

    def print_error(self, message):
        msg = str(message)
        self._set_status("Error")
        self._set_activity(msg)
        self._run_on_ui(lambda: messagebox.showerror("Error", msg) if messagebox else None)

    def print_info(self, message):
        msg = str(message)
        self._set_activity(msg)

    def reset_for_new_session(self):
        """Reset UI for a new game session."""
        def _do():
            self._phase = "waiting"
            self._set_var(self._round_var, "Waiting")
            self._set_var(self._status_var, "Waiting for server...")
            self._set_var(self._advice_var, "")
            self._set_var(self._result_var, "")
            self._set_var(self._result_style_var, "neutral")
            self._clear_cards()
            # Reset stats display
            self._set_var(self._stat_rounds_var, "0")
            self._set_var(self._stat_wins_var, "0")
            self._set_var(self._stat_losses_var, "0")
            self._set_var(self._stat_ties_var, "0")
            self._set_var(self._stat_win_rate_var, "0.00%")
            self._set_var(self._stat_hits_var, "0")
            self._set_var(self._stat_stands_var, "0")
        self._run_on_ui(_do)
        self._set_activity("Starting new session...")

    def get_rounds_input(self):
        return int(self._call_ui_sync(self._ask_rounds_modal))

    def get_decision_input(self):
        return str(self._call_ui_sync(self._ask_decision_modal))

    def print_invalid_decision(self):
        self._set_status("Invalid input")
        self._set_activity("Invalid decision. Please choose Hit or Stand.")
        self._run_on_ui(lambda: messagebox.showwarning("Invalid input", "Please choose exactly: Hit or Stand.") if messagebox else None)

    def get_betting_mode_choice(self):
        """Ask user if they want to enable betting mode."""
        return bool(self._call_ui_sync(self._ask_betting_mode_modal))

    def get_bet_amount(self, balance):
        """Ask user for bet amount."""
        return int(self._call_ui_sync(lambda: self._ask_bet_amount_modal(balance)))

    def get_play_again_choice(self):
        """Ask user if they want to play another session."""
        return bool(self._call_ui_sync(self._ask_play_again_modal))

    # -----------------------------
    # Tk thread + plumbing
    # -----------------------------
    def _ensure_tk_available(self):
        if tk is None:
            raise RuntimeError(f"Tkinter is not available: {_tk_import_error}")

    def _start_ui_thread(self):
        t = threading.Thread(target=self._ui_thread_main, name="BlackjackUIThread", daemon=True)
        t.start()

    def _ui_thread_main(self):
        root = tk.Tk()
        root.title("Socket-Aces — Blackjack")
        root.minsize(860, 560)

        # Window background (simple dark theme)
        try:
            root.configure(bg="#0b1220")
        except Exception:
            pass

        # Variables
        self._round_var = tk.StringVar(value="Waiting")
        self._status_var = tk.StringVar(value="Ready")
        self._activity_var = tk.StringVar(value="")
        self._server_var = tk.StringVar(value="No server yet")
        self._advice_var = tk.StringVar(value="")
        self._result_var = tk.StringVar(value="")
        self._result_style_var = tk.StringVar(value="neutral")

        self._stat_rounds_var = tk.StringVar(value="0")
        self._stat_wins_var = tk.StringVar(value="0")
        self._stat_losses_var = tk.StringVar(value="0")
        self._stat_ties_var = tk.StringVar(value="0")
        self._stat_win_rate_var = tk.StringVar(value="0.00%")
        self._stat_hits_var = tk.StringVar(value="0")
        self._stat_stands_var = tk.StringVar(value="0")

        self._root = root
        self._apply_theme()
        self._build_layout(root)

        root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._ui_ready.set()
        root.after(40, self._drain_actions)
        root.mainloop()

    def _on_close(self):
        self._closed.set()
        try:
            if self._root is not None:
                self._root.destroy()
        finally:
            # Force exit entire application including all threads
            import os
            os._exit(0)

    def _drain_actions(self):
        if self._root is None:
            return
        try:
            while True:
                fn = self._action_queue.get_nowait()
                try:
                    fn()
                except Exception:
                    # Never crash UI loop from a single bad render call.
                    pass
        except queue.Empty:
            pass
        if not self._closed.is_set():
            self._root.after(40, self._drain_actions)

    def _run_on_ui(self, fn: Callable[[], None]):
        if self._closed.is_set():
            return
        self._action_queue.put(fn)

    def _call_ui_sync(self, fn: Callable[[], Any]) -> Any:
        if self._closed.is_set():
            raise SystemExit(0)
        call = _SyncCall(fn=fn, done=threading.Event())

        def _wrapped():
            try:
                call.result = call.fn()
            except BaseException as e:
                call.error = e
            finally:
                call.done.set()

        self._run_on_ui(_wrapped)
        call.done.wait()
        if call.error:
            raise call.error
        return call.result

    # -----------------------------
    # Layout / rendering helpers
    # -----------------------------
    def _apply_theme(self):
        if ttk is None or self._root is None:
            return
        style = ttk.Style(self._root)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure("TLabel", padding=(2, 2), foreground="#e5e7eb", background="#0b1220")
        style.configure("TFrame", background="#0b1220")
        style.configure("TLabelframe", background="#0b1220", foreground="#e5e7eb")
        style.configure("TLabelframe.Label", background="#0b1220", foreground="#e5e7eb")

        style.configure("Top.TFrame", background="#0b1220")
        style.configure("Panel.TLabelframe", background="#111827", foreground="#e5e7eb")
        style.configure("Panel.TLabelframe.Label", background="#111827", foreground="#e5e7eb")

        style.configure("Header.TLabel", font=("Segoe UI", 16, "bold"))
        style.configure("Subheader.TLabel", font=("Segoe UI", 10))
        style.configure("Status.TLabel", font=("Segoe UI", 10, "bold"), foreground="#93c5fd")
        style.configure("Advice.TLabel", font=("Segoe UI", 10, "italic"))
        style.configure("CardOwner.TLabel", font=("Segoe UI", 9, "bold"))
        style.configure("Action.TButton", padding=(12, 8), font=("Segoe UI", 10, "bold"))

        style.configure("Result.TLabel", font=("Segoe UI", 14, "bold"), foreground="#e5e7eb")
        style.configure("ResultWin.TLabel", font=("Segoe UI", 14, "bold"), foreground="#34d399")
        style.configure("ResultLoss.TLabel", font=("Segoe UI", 14, "bold"), foreground="#f87171")
        style.configure("ResultTie.TLabel", font=("Segoe UI", 14, "bold"), foreground="#fbbf24")

    def _build_layout(self, root: Any):
        root.columnconfigure(0, weight=3)
        root.columnconfigure(1, weight=2)
        root.rowconfigure(1, weight=1)

        # Top bar
        top = ttk.Frame(root, padding=(14, 12), style="Top.TFrame")
        top.grid(row=0, column=0, columnspan=2, sticky="nsew")
        top.columnconfigure(0, weight=1)
        top.columnconfigure(1, weight=1)
        top.columnconfigure(2, weight=1)

        ttk.Label(top, text="Socket-Aces — Blackjack", style="Header.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(top, textvariable=self._round_var, style="Header.TLabel").grid(row=0, column=1)
        ttk.Label(top, textvariable=self._server_var, style="Subheader.TLabel").grid(row=0, column=2, sticky="e")

        ttk.Label(top, textvariable=self._status_var, style="Status.TLabel").grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Label(top, textvariable=self._activity_var, style="Subheader.TLabel").grid(row=1, column=1, sticky="n")
        ttk.Label(top, textvariable=self._advice_var, style="Advice.TLabel").grid(row=1, column=2, sticky="e", pady=(6, 0))

        # Left: Cards + log
        left = ttk.Frame(root, padding=(14, 0, 10, 14))
        left.grid(row=1, column=0, sticky="nsew")
        left.rowconfigure(1, weight=1)
        left.columnconfigure(0, weight=1)

        cards_group = ttk.LabelFrame(left, text="Table", padding=(12, 10), style="Panel.TLabelframe")
        cards_group.grid(row=0, column=0, sticky="nsew", pady=(0, 10))
        cards_group.columnconfigure(0, weight=1)

        # Two clear hands: Dealer (top) and Player (bottom)
        hands = ttk.Frame(cards_group)
        hands.grid(row=0, column=0, sticky="nsew")
        hands.columnconfigure(0, weight=1)
        hands.columnconfigure(1, weight=1)

        dealer_group = ttk.LabelFrame(hands, text="Dealer", padding=(10, 8), style="Panel.TLabelframe")
        dealer_group.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        dealer_group.columnconfigure(0, weight=1)

        player_group = ttk.LabelFrame(hands, text="Player", padding=(10, 8), style="Panel.TLabelframe")
        player_group.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        player_group.columnconfigure(0, weight=1)

        self._dealer_cards_container = tk.Frame(dealer_group)
        self._dealer_cards_container.grid(row=0, column=0, sticky="nsew")

        self._player_cards_container = tk.Frame(player_group)
        self._player_cards_container.grid(row=0, column=0, sticky="nsew")

        # No game log (per requirement)
        left.rowconfigure(1, weight=0)

        # Right: actions + stats
        right = ttk.Frame(root, padding=(10, 0, 14, 14))
        right.grid(row=1, column=1, sticky="nsew")
        right.rowconfigure(2, weight=1)
        right.columnconfigure(0, weight=1)

        actions = ttk.LabelFrame(right, text="Actions", padding=(12, 10), style="Panel.TLabelframe")
        actions.grid(row=0, column=0, sticky="nsew", pady=(0, 10))
        actions.columnconfigure(0, weight=1)

        self._hit_btn = ttk.Button(actions, text="Hit", style="Action.TButton", command=lambda: self._set_decision("Hit"))
        self._hit_btn.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self._stand_btn = ttk.Button(actions, text="Stand", style="Action.TButton", command=lambda: self._set_decision("Stand"))
        self._stand_btn.grid(row=1, column=0, sticky="ew")

        hint = ttk.Label(actions, text="Tip: use H / S keys", style="Subheader.TLabel")
        hint.grid(row=2, column=0, sticky="w", pady=(10, 0))

        result = ttk.LabelFrame(right, text="Result", padding=(12, 10), style="Panel.TLabelframe")
        result.grid(row=1, column=0, sticky="nsew", pady=(0, 10))
        result.columnconfigure(0, weight=1)

        self._result_label = ttk.Label(result, textvariable=self._result_var, style="Result.TLabel", anchor="center", justify="center")
        self._result_label.grid(row=0, column=0, sticky="ew")

        stats = ttk.LabelFrame(right, text="Statistics", padding=(12, 10), style="Panel.TLabelframe")
        stats.grid(row=2, column=0, sticky="nsew")
        stats.columnconfigure(0, weight=1)
        stats.columnconfigure(1, weight=1)

        self._build_stats_grid(stats)

        # Keyboard shortcuts
        root.bind_all("<h>", lambda _e: self._set_decision("Hit"))
        root.bind_all("<H>", lambda _e: self._set_decision("Hit"))
        root.bind_all("<s>", lambda _e: self._set_decision("Stand"))
        root.bind_all("<S>", lambda _e: self._set_decision("Stand"))

        self._set_decision_buttons_enabled(False)

        # Update result label color based on result style.
        def _refresh_result_style(*_args):
            style_key = (self._result_style_var.get() if self._result_style_var else "neutral")
            style = {
                "win": "ResultWin.TLabel",
                "loss": "ResultLoss.TLabel",
                "tie": "ResultTie.TLabel",
                "neutral": "Result.TLabel",
            }.get(style_key, "Result.TLabel")
            try:
                self._result_label.configure(style=style)
            except Exception:
                pass

        if self._result_style_var is not None:
            self._result_style_var.trace_add("write", _refresh_result_style)
            _refresh_result_style()

    def _set_var(self, var: Optional[Any], value: str):
        if var is None:
            return
        var.set(value)

    def _set_status(self, text: str):
        self._run_on_ui(lambda: self._set_var(self._status_var, text))

    def _set_activity(self, text: str):
        self._run_on_ui(lambda: self._set_var(self._activity_var, text))

    def _clear_cards(self):
        for container in (self._dealer_cards_container, self._player_cards_container):
            if container is None:
                continue
            for child in list(container.winfo_children()):
                child.destroy()

    def _add_card_widget(self, owner: str, rank: str, suit: str, is_red: bool):
        container = self._player_cards_container if owner == "Player" else self._dealer_cards_container
        if container is None:
            return

        wrapper = tk.Frame(container, padx=6, pady=6)
        wrapper.pack(side="left", anchor="n")

        fg = "#f87171" if is_red else "#e5e7eb"
        bg = "#0f172a"

        canvas = tk.Canvas(wrapper, width=110, height=150, highlightthickness=0, bg=container.cget("bg"))
        canvas.pack()

        # Card background
        canvas.create_rectangle(6, 6, 104, 144, fill=bg, outline="#334155", width=2)

        # Corner rank/suit
        canvas.create_text(18, 20, text=rank, fill=fg, font=("Segoe UI", 12, "bold"), anchor="w")
        canvas.create_text(18, 38, text=suit, fill=fg, font=("Segoe UI", 12, "bold"), anchor="w")

        # Center suit
        canvas.create_text(55, 80, text=suit, fill=fg, font=("Segoe UI", 38, "bold"))

        # Bottom-right rank/suit
        canvas.create_text(92, 120, text=suit, fill=fg, font=("Segoe UI", 12, "bold"), anchor="e")
        canvas.create_text(92, 136, text=rank, fill=fg, font=("Segoe UI", 12, "bold"), anchor="e")

    def _result_text(self, result_code: int) -> tuple[str, str]:
        if result_code == 0x3:
            return "YOU WIN", "win"
        if result_code == 0x2:
            return "YOU LOST", "loss"
        if result_code == 0x1:
            return "TIE", "tie"
        return f"Unknown result code: {result_code}", "neutral"

    def _build_stats_grid(self, parent: Any):
        def _row(r: int, label: str, var: Any):
            ttk.Label(parent, text=label, style="Subheader.TLabel").grid(row=r, column=0, sticky="w", pady=2)
            ttk.Label(parent, textvariable=var, font=("Consolas", 11, "bold")).grid(row=r, column=1, sticky="e", pady=2)

        if self._stat_rounds_var is None:
            return

        _row(0, "Rounds played", self._stat_rounds_var)
        _row(1, "Wins", self._stat_wins_var)
        _row(2, "Losses", self._stat_losses_var)
        _row(3, "Ties", self._stat_ties_var)
        _row(4, "Win rate", self._stat_win_rate_var)
        _row(5, "Hits", self._stat_hits_var)
        _row(6, "Stands", self._stat_stands_var)

    # -----------------------------
    # Modal inputs (run on UI thread)
    # -----------------------------
    def _ask_rounds_modal(self) -> int:
        if self._root is None:
            return 1

        dlg = tk.Toplevel(self._root)
        dlg.title("Rounds")
        dlg.transient(self._root)
        dlg.grab_set()
        dlg.resizable(False, False)

        ttk.Label(dlg, text="How many rounds do you want to play?", padding=(14, 12)).grid(row=0, column=0, columnspan=2, sticky="w")
        value_var = tk.StringVar(value="5")
        entry = ttk.Entry(dlg, textvariable=value_var, width=12)
        entry.grid(row=1, column=0, padx=(14, 8), pady=(0, 12), sticky="w")
        entry.focus_set()

        result = {"value": None}

        def _ok():
            raw = (value_var.get() or "").strip()
            if raw.isdigit() and int(raw) > 0:
                result["value"] = int(raw)
                dlg.destroy()
            else:
                if messagebox:
                    messagebox.showwarning("Invalid", "Please enter a positive integer.")

        def _cancel():
            # Preserve old behavior: force a valid number.
            if messagebox:
                messagebox.showwarning("Required", "Rounds is required to start a session.")

        ttk.Button(dlg, text="Start", command=_ok).grid(row=1, column=1, padx=(8, 14), pady=(0, 12), sticky="e")
        dlg.protocol("WM_DELETE_WINDOW", _cancel)
        dlg.bind("<Return>", lambda _e: _ok())

        self._root.wait_window(dlg)
        return int(result["value"] or 1)

    def _ask_decision_modal(self) -> str:
        if self._root is None:
            return "Stand"

        self._phase = "player"
        self._decision_var = tk.StringVar(value="")
        self._set_decision_buttons_enabled(True)
        self._set_var(self._status_var, "Your move: Hit or Stand")

        # This runs a nested event loop until decision_var changes.
        self._root.wait_variable(self._decision_var)
        value = (self._decision_var.get() or "").strip().title()
        self._set_decision_buttons_enabled(False)
        return value or "Stand"

    def _between_rounds_pause_if_needed(self) -> None:
        """Runs on the UI thread.

        If a previous round result exists, show a modal summary and wait for
        the user to proceed. This lets the player actually see the last round
        outcome before the next round clears the table.
        """
        if self._root is None or self._result_var is None:
            return

        result_text = (self._result_var.get() or "").strip()
        if not result_text:
            return

        dlg = tk.Toplevel(self._root)
        dlg.title("Round Summary")
        dlg.transient(self._root)
        dlg.grab_set()
        dlg.resizable(False, False)

        outer = ttk.Frame(dlg, padding=(16, 14))
        outer.grid(row=0, column=0, sticky="nsew")
        outer.columnconfigure(0, weight=1)

        ttk.Label(outer, text="Last Round Result", style="Header.TLabel").grid(row=0, column=0, sticky="w")

        # Result banner
        banner = ttk.Frame(outer, padding=(12, 10))
        banner.grid(row=1, column=0, sticky="ew", pady=(10, 10))
        banner.columnconfigure(0, weight=1)

        style_key = (self._result_style_var.get() if self._result_style_var else "neutral")
        label_style = {
            "win": "ResultWin.TLabel",
            "loss": "ResultLoss.TLabel",
            "tie": "ResultTie.TLabel",
            "neutral": "Result.TLabel",
        }.get(style_key, "Result.TLabel")

        ttk.Label(banner, text=result_text, style=label_style, anchor="center", justify="center").grid(
            row=0, column=0, sticky="ew"
        )

        # Stats snapshot
        stats = ttk.LabelFrame(outer, text="Statistics", padding=(12, 10), style="Panel.TLabelframe")
        stats.grid(row=2, column=0, sticky="ew")
        stats.columnconfigure(0, weight=1)
        stats.columnconfigure(1, weight=1)

        def _row(r: int, label: str, var: Optional[Any]):
            ttk.Label(stats, text=label, style="Subheader.TLabel").grid(row=r, column=0, sticky="w", pady=2)
            ttk.Label(stats, text=(var.get() if var else ""), font=("Consolas", 11, "bold")).grid(
                row=r, column=1, sticky="e", pady=2
            )

        _row(0, "Rounds played", self._stat_rounds_var)
        _row(1, "Wins", self._stat_wins_var)
        _row(2, "Losses", self._stat_losses_var)
        _row(3, "Ties", self._stat_ties_var)
        _row(4, "Win rate", self._stat_win_rate_var)
        _row(5, "Hits", self._stat_hits_var)
        _row(6, "Stands", self._stat_stands_var)

        # Continue button
        btn_row = ttk.Frame(outer)
        btn_row.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        btn_row.columnconfigure(0, weight=1)

        def _close():
            try:
                dlg.destroy()
            except Exception:
                pass

        ttk.Button(btn_row, text="Next Round", style="Action.TButton", command=_close).grid(
            row=0, column=0, sticky="e"
        )

        dlg.protocol("WM_DELETE_WINDOW", _close)
        dlg.bind("<Return>", lambda _e: _close())
        dlg.bind("<Escape>", lambda _e: _close())

        # Center dialog over main window
        try:
            dlg.update_idletasks()
            x = self._root.winfo_rootx() + (self._root.winfo_width() // 2) - (dlg.winfo_width() // 2)
            y = self._root.winfo_rooty() + (self._root.winfo_height() // 2) - (dlg.winfo_height() // 2)
            dlg.geometry(f"+{max(0, x)}+{max(0, y)}")
        except Exception:
            pass

        self._root.wait_window(dlg)

    def _set_decision_buttons_enabled(self, enabled: bool):
        if self._hit_btn is not None:
            self._hit_btn.configure(state=("normal" if enabled else "disabled"))
        if self._stand_btn is not None:
            self._stand_btn.configure(state=("normal" if enabled else "disabled"))

    def _set_decision(self, value: str):
        if value not in ("Hit", "Stand"):
            return
        if self._decision_var is None:
            return
        self._decision_var.set(value)

    def _ask_betting_mode_modal(self) -> bool:
        """Modal dialog asking if user wants betting mode."""
        dlg = tk.Toplevel(self._root)
        dlg.title("Game Mode")
        dlg.transient(self._root)
        dlg.grab_set()
        
        try:
            dlg.configure(bg="#1a2332")
        except Exception:
            pass

        outer = ttk.Frame(dlg, padding=24)
        outer.grid(row=0, column=0, sticky="nsew")
        dlg.columnconfigure(0, weight=1)
        dlg.rowconfigure(0, weight=1)

        ttk.Label(outer, text="Choose Game Mode", font=("Segoe UI", 14, "bold")).grid(
            row=0, column=0, columnspan=2, pady=(0, 16)
        )

        ttk.Label(outer, text="Play with betting to track your winnings!", font=("Segoe UI", 10)).grid(
            row=1, column=0, columnspan=2, pady=(0, 16)
        )

        result = {"value": False}

        def _no_betting():
            result["value"] = False
            dlg.destroy()

        def _with_betting():
            result["value"] = True
            dlg.destroy()

        ttk.Button(outer, text="Play Without Betting", command=_no_betting).grid(
            row=2, column=0, padx=5, pady=5, sticky="ew"
        )
        ttk.Button(outer, text="Play With Betting ($1000)", style="Action.TButton", command=_with_betting).grid(
            row=2, column=1, padx=5, pady=5, sticky="ew"
        )

        dlg.protocol("WM_DELETE_WINDOW", _no_betting)

        try:
            dlg.update_idletasks()
            x = self._root.winfo_rootx() + (self._root.winfo_width() // 2) - (dlg.winfo_width() // 2)
            y = self._root.winfo_rooty() + (self._root.winfo_height() // 2) - (dlg.winfo_height() // 2)
            dlg.geometry(f"+{max(0, x)}+{max(0, y)}")
        except Exception:
            pass

        self._root.wait_window(dlg)
        return result["value"]

    def _ask_bet_amount_modal(self, balance: int) -> int:
        """Modal dialog asking for bet amount."""
        dlg = tk.Toplevel(self._root)
        dlg.title("Place Your Bet")
        dlg.transient(self._root)
        dlg.grab_set()
        
        try:
            dlg.configure(bg="#1a2332")
        except Exception:
            pass

        outer = ttk.Frame(dlg, padding=24)
        outer.grid(row=0, column=0, sticky="nsew")
        dlg.columnconfigure(0, weight=1)
        dlg.rowconfigure(0, weight=1)

        ttk.Label(outer, text="Place Your Bet", font=("Segoe UI", 14, "bold")).grid(
            row=0, column=0, columnspan=2, pady=(0, 16)
        )

        ttk.Label(outer, text=f"Current Balance: ${balance}", font=("Segoe UI", 11)).grid(
            row=1, column=0, columnspan=2, pady=(0, 12)
        )

        bet_var = tk.StringVar(value="10")
        result = {"value": 10}

        def _submit():
            try:
                bet = int(bet_var.get())
                if bet > 0 and bet <= balance:
                    result["value"] = bet
                    dlg.destroy()
                else:
                    messagebox.showwarning("Invalid Bet", f"Please enter a bet between $1 and ${balance}")
            except ValueError:
                messagebox.showwarning("Invalid Bet", "Please enter a valid number")

        # Quick bet buttons
        ttk.Label(outer, text="Quick Bets:").grid(row=2, column=0, columnspan=2, sticky="w", pady=(0, 5))
        
        btn_frame = ttk.Frame(outer)
        btn_frame.grid(row=3, column=0, columnspan=2, pady=(0, 12))
        
        for i, amount in enumerate([10, 25, 50, 100]):
            if amount <= balance:
                ttk.Button(btn_frame, text=f"${amount}", 
                          command=lambda a=amount: (bet_var.set(str(a)), _submit())).grid(
                    row=0, column=i, padx=2
                )

        ttk.Label(outer, text="Custom Amount:").grid(row=4, column=0, sticky="w", pady=(0, 5))
        bet_entry = ttk.Entry(outer, textvariable=bet_var, width=15, font=("Segoe UI", 11))
        bet_entry.grid(row=5, column=0, columnspan=2, pady=(0, 16), sticky="ew")
        bet_entry.focus()

        ttk.Button(outer, text="Place Bet", style="Action.TButton", command=_submit).grid(
            row=6, column=0, columnspan=2, pady=5, sticky="ew"
        )

        dlg.protocol("WM_DELETE_WINDOW", _submit)
        dlg.bind("<Return>", lambda _e: _submit())
        bet_entry.bind("<Return>", lambda _e: _submit())

        try:
            dlg.update_idletasks()
            x = self._root.winfo_rootx() + (self._root.winfo_width() // 2) - (dlg.winfo_width() // 2)
            y = self._root.winfo_rooty() + (self._root.winfo_height() // 2) - (dlg.winfo_height() // 2)
            dlg.geometry(f"+{max(0, x)}+{max(0, y)}")
        except Exception:
            pass

        self._root.wait_window(dlg)
        return result["value"]

    def _ask_play_again_modal(self) -> bool:
        """Modal dialog asking if user wants to play another session."""
        dlg = tk.Toplevel(self._root)
        dlg.title("Session Complete")
        dlg.transient(self._root)
        dlg.grab_set()
        
        try:
            dlg.configure(bg="#1a2332")
        except Exception:
            pass

        outer = ttk.Frame(dlg, padding=24)
        outer.grid(row=0, column=0, sticky="nsew")
        dlg.columnconfigure(0, weight=1)
        dlg.rowconfigure(0, weight=1)

        ttk.Label(outer, text="Game session finished!", font=("Segoe UI", 14, "bold")).grid(
            row=0, column=0, columnspan=2, pady=(0, 16)
        )

        ttk.Label(outer, text="Would you like to play another session?").grid(
            row=1, column=0, columnspan=2, pady=(0, 16)
        )

        result = {"value": False}

        def _yes():
            result["value"] = True
            dlg.destroy()

        def _no():
            result["value"] = False
            dlg.destroy()

        ttk.Button(outer, text="Yes, Play Again", style="Action.TButton", command=_yes).grid(
            row=2, column=0, padx=5, pady=5, sticky="ew"
        )
        ttk.Button(outer, text="No, Exit", command=_no).grid(
            row=2, column=1, padx=5, pady=5, sticky="ew"
        )

        dlg.protocol("WM_DELETE_WINDOW", _no)

        try:
            dlg.update_idletasks()
            x = self._root.winfo_rootx() + (self._root.winfo_width() // 2) - (dlg.winfo_width() // 2)
            y = self._root.winfo_rooty() + (self._root.winfo_height() // 2) - (dlg.winfo_height() // 2)
            dlg.geometry(f"+{max(0, x)}+{max(0, y)}")
        except Exception:
            pass

        self._root.wait_window(dlg)
        return result["value"]
