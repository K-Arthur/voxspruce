"""Native GTK4/libadwaita views. All controller calls stay on the UI thread."""

import math
import shutil
import subprocess
import threading
from dataclasses import replace
from importlib.resources import files
from uuid import uuid4

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gtk, Pango

from .commands import CustomShortcut, command_catalogue
from .domain import DomainError, Mode, State
from .storage import SettingsError, SettingsStore
from .ui_model import action_details, can_capture, create_controller, dependency_status


def label(text="", *, title=False):
    widget = Gtk.Label(
        label=text,
        xalign=0,
        wrap=True,
        selectable=True,
        wrap_mode=Pango.WrapMode.WORD_CHAR,
    )
    if title:
        widget.add_css_class("title-2")
    return widget


class AccessibleHeading(Gtk.Label):
    """A heading role isolated to headings rather than every Gtk.Label."""

    __gtype_name__ = "WvcAccessibleHeading"

    def __init__(self, text, *, level=2):
        super().__init__(
            label=text,
            xalign=0,
            wrap=level >= 2,
            wrap_mode=Pango.WrapMode.WORD_CHAR,
        )
        if hasattr(Gtk.AccessibleRole, "HEADING"):
            self.set_accessible_role(Gtk.AccessibleRole.HEADING)
        if hasattr(Gtk.AccessibleProperty, "LEVEL"):
            self.update_property([Gtk.AccessibleProperty.LEVEL], [level])
        if level >= 2:
            self.add_css_class("title-2")


class AccessibleStatus(Gtk.Label):
    """A status role isolated to the live status label."""

    __gtype_name__ = "WvcAccessibleStatus"

    def __init__(self):
        super().__init__(xalign=0, wrap=True, wrap_mode=Pango.WrapMode.WORD_CHAR)
        if hasattr(Gtk.AccessibleRole, "STATUS"):
            self.set_accessible_role(Gtk.AccessibleRole.STATUS)


class AccessibleGroup(Gtk.Box):
    """A named semantic group used for each labelled UI section."""

    __gtype_name__ = "WvcAccessibleGroup"

    def __init__(self, title):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        if hasattr(Gtk.AccessibleRole, "GROUP"):
            self.set_accessible_role(Gtk.AccessibleRole.GROUP)
        self.update_property([Gtk.AccessibleProperty.LABEL], [title])


def button(text, callback, *, primary=False):
    widget = Gtk.Button(height_request=44)
    widget.set_child(
        Gtk.Label(
            label=text,
            wrap=True,
            wrap_mode=Pango.WrapMode.WORD_CHAR,
            justify=Gtk.Justification.CENTER,
        )
    )
    widget.update_property([Gtk.AccessibleProperty.LABEL], [text])
    widget.connect("clicked", lambda *_: callback())
    if primary:
        widget.add_css_class("suggested-action")
    return widget


def checkbox(label, active=False):
    widget = Gtk.CheckButton(active=active)
    widget.set_child(
        Gtk.Label(label=label, wrap=True, wrap_mode=Pango.WrapMode.WORD_CHAR, xalign=0)
    )
    widget.update_property([Gtk.AccessibleProperty.LABEL], [label])
    return widget


def section(parent, title, description=""):
    box = AccessibleGroup(title)
    box.append(AccessibleHeading(title))
    if description:
        box.append(label(description))
    parent.append(box)
    return box


def entry(parent, title, *, limit=4096):
    parent.append(label(title))
    widget = Gtk.Entry(max_length=limit, hexpand=True)
    widget.update_property([Gtk.AccessibleProperty.LABEL], [title])
    parent.append(widget)
    return widget


class VoiceWindow(Adw.ApplicationWindow):
    def __init__(
        self, *, application=None, store=None, controller_factory=create_controller
    ):
        super().__init__(
            application=application,
            title="Wayland Voice Control",
            default_width=780,
            default_height=820,
        )
        self.store = store or SettingsStore()
        self.controller_factory = controller_factory
        self.controller = controller_factory(practice=True, store=self.store)
        self.unsubscribe = None
        self._rendering = False
        self._loading_settings = False
        self._settings_dirty = False
        self._held = False
        self._hold_pressed = False
        self._toggle_capture_started = False
        self._closed = False
        self._reviewed_id = None
        self._custom_id = None
        self._catalogue_signature = None
        self._reader = None
        self._reader_action_id = None
        self._reader_generation = 0
        self._chooser = None
        self._last_announced_status = None
        Gtk.IconTheme.get_for_display(self.get_display()).add_search_path(
            str(files("wayland_voice_control").joinpath("resources/icons"))
        )
        self.set_icon_name("io.github.wayland_voice_control")
        self._build()
        self.unsubscribe = self.controller.subscribe(self.render)
        self.connect("close-request", self._close)
        self.connect("notify::is-active", self._active_changed)
        keys = Gtk.EventControllerKey()
        keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", self._window_key)
        keys.connect("key-released", self._window_key_release)
        self.add_controller(keys)

    def _build(self):
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        header = Adw.HeaderBar()
        header.set_title_widget(AccessibleHeading("Wayland Voice Control", level=1))
        self.stop_button = button("Stop", self.stop_action)
        self.stop_button.set_icon_name("process-stop-symbolic")
        self.stop_button.set_label("Stop")
        self.stop_button.add_css_class("destructive-action")
        self.stop_button.set_tooltip_text(
            "Stop, discard content and revoke live grants"
        )
        header.pack_end(self.stop_button)
        root.append(header)
        self.stack = Gtk.Stack()
        self.stack.set_vexpand(True)
        switcher = Gtk.StackSwitcher(stack=self.stack, halign=Gtk.Align.CENTER)
        switcher.set_margin_top(8)
        switcher.set_margin_bottom(8)
        root.append(switcher)
        for name, title, build in [
            ("voice", "Voice", self._voice),
            ("commands", "Commands", self._commands),
            ("setup", "Setup", self._setup),
        ]:
            content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
            for edge in ["top", "bottom", "start", "end"]:
                getattr(content, "set_margin_" + edge)(24)
            clamp = Adw.Clamp(maximum_size=760, tightening_threshold=540)
            clamp.set_child(content)
            scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
            scroll.set_child(clamp)
            self.stack.add_titled(scroll, name, title)
            build(content)
        root.append(self.stack)
        self.set_content(root)

    def _voice(self, parent):
        modes = section(
            parent,
            "Speak, review, confirm",
            "Offline speech. Nothing records on launch. Escape cancels; Stop revokes live grants.",
        )
        self.practice_switch = checkbox(
            label="Practice mode — simulate input only", active=True
        )
        self.practice_switch.connect("toggled", self._switch_mode)
        modes.append(self.practice_switch)
        self.mode_status = label()
        modes.append(self.mode_status)
        self.command_mode = checkbox(label="Commands mode (exact phrases only)")
        self.command_mode.connect("toggled", self._command_changed)
        modes.append(self.command_mode)
        self.readiness = label()
        modes.append(self.readiness)
        self.status = AccessibleStatus()
        self.status.add_css_class("heading")
        modes.append(self.status)
        self.practice_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.practice_entry = entry(
            self.practice_box,
            "Typed practice example (up to 4000 characters)",
            limit=4000,
        )
        self.practice_entry.set_text("Hello from offline practice")
        self.practice_review = button(
            "Review practice example", self.review_practice, primary=True
        )
        self.practice_box.append(self.practice_review)
        modes.append(self.practice_box)
        self.hold_button = Gtk.Button(
            label="Hold to talk · Space while focused", height_request=56
        )
        self.hold_button.add_css_class("suggested-action")
        self.hold_button.connect("notify::has-focus", self._hold_focus_changed)
        gesture = Gtk.GestureClick(button=1)
        gesture.connect("pressed", lambda *_: self.hold_begin())
        gesture.connect("released", lambda *_: self.hold_end())
        gesture.connect("stopped", lambda *_: self._cancel_hold())
        self.hold_button.add_controller(gesture)
        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self._hold_key)
        self.hold_button.add_controller(keys)
        modes.append(self.hold_button)
        self.toggle_capture_button = button(
            "Start recording without holding", self.toggle_capture_action
        )
        self.toggle_capture_button.set_size_request(-1, 56)
        modes.append(self.toggle_capture_button)
        modes.append(
            label(
                "Tap once to start and again to finish. Leaving this window cancels capture; the duration cap also stops it."
            )
        )
        self.draft = label()
        self.draft.add_css_class("dim-label")
        modes.append(label("Live provisional draft · never approved or sent"))
        modes.append(self.draft)
        review = section(
            parent,
            "Review the complete action",
            "Release to get the final result. Check every word and the destination before confirming.",
        )
        self.review_details = label()
        review.append(self.review_details)
        self.editor = Gtk.TextView(
            editable=False,
            cursor_visible=False,
            wrap_mode=Gtk.WrapMode.WORD_CHAR,
            top_margin=12,
            bottom_margin=12,
            left_margin=12,
            right_margin=12,
        )
        self.editor.update_property(
            [Gtk.AccessibleProperty.LABEL], ["Complete transcript editor"]
        )
        edit_scroll = Gtk.ScrolledWindow(
            min_content_height=112,
            max_content_height=240,
            propagate_natural_height=True,
        )
        edit_scroll.set_child(self.editor)
        review.append(edit_scroll)
        self.edit_button = button("Edit transcript…", self.begin_edit)
        review.append(self.edit_button)
        self.rereview_button = button("Re-review complete edit", self.finish_edit)
        review.append(self.rereview_button)
        self.confirm_button = button(
            "Confirm reviewed action", self.confirm, primary=True
        )
        review.append(self.confirm_button)
        self.second_button = button(
            "Second confirmation: allow this high-risk action", self.confirm_second
        )
        self.second_button.add_css_class("destructive-action")
        review.append(self.second_button)
        self.countdown = label()
        review.append(self.countdown)
        review.append(button("Cancel · Escape", self.cancel_action))
        self.readback_button = button(
            "Read reviewed action aloud (espeak-ng)", self.read_back
        )
        self.readback_button.set_tooltip_text(
            "Optional local speech; sends text to espeak-ng through stdin only"
        )
        review.append(self.readback_button)
        self.practice_output = label("Practice output: no simulated action yet.")
        parent.append(self.practice_output)

    def _commands(self, parent):
        section(
            parent,
            "Exact command phrases",
            "Say one whole phrase in Commands mode. Dictation always stays literal. "
            "High-risk actions and every custom shortcut require two separate confirmations.",
        )
        self.command_search = Gtk.SearchEntry(
            placeholder_text="Filter phrases, keys and descriptions"
        )
        self.command_search.update_property(
            [Gtk.AccessibleProperty.LABEL], ["Filter commands"]
        )
        self.command_search.connect("search-changed", lambda *_: self._fill_commands())
        parent.append(self.command_search)
        self.command_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        parent.append(self.command_list)
        manager = section(
            parent,
            "Custom voice shortcut",
            "Map one exact phrase to one keyboard chord. Its effect depends on the destination app; "
            "it could submit, delete or close content. Every custom action is high risk. "
            "Saving or deleting discards pending work. At most 100 entries.",
        )
        self.custom_phrase = entry(
            manager, "Voice phrase (1–120 characters)", limit=120
        )
        self.custom_chord = entry(
            manager, "One chord · e.g. Ctrl+S, Alt+F4, Shift+Tab", limit=64
        )
        self.custom_description = entry(
            manager, "Description (optional, up to 240 characters)", limit=240
        )
        self.custom_enabled = checkbox(label="Enabled", active=True)
        manager.append(self.custom_enabled)
        self.custom_preview = label()
        manager.append(self.custom_preview)
        self.custom_error = label()
        self.custom_error.add_css_class("error")
        manager.append(self.custom_error)
        for widget in (self.custom_phrase, self.custom_chord, self.custom_description):
            widget.connect("changed", lambda *_: self.preview_custom())
        self.custom_new = button("New shortcut / clear editor", self.new_custom)
        self.custom_save = button("Save shortcut", self.save_custom, primary=True)
        self.custom_delete = button("Delete selected shortcut", self.delete_custom)
        manager.append(self.custom_new)
        manager.append(self.custom_save)
        manager.append(self.custom_delete)
        manager.append(
            label(
                "Allowed keys: letters A–Z, digits, Space, Return, Tab, Escape, BackSpace, Delete, "
                "Home, End, arrows, PageUp, PageDown and F1–F12. Optional Ctrl, Alt, Shift, Super. "
                "No scripts, multiple strokes or replacement of built-in phrases."
            )
        )
        self.new_custom()

    def _setup(self, parent):
        model = section(
            parent,
            "1 · Prepare an offline model",
            "Download and extract a Vosk model yourself, then choose its local directory. "
            "Preparation loads it without recording. Model files are never downloaded by this app.",
        )
        self.dependencies_status = label(dependency_status())
        model.append(self.dependencies_status)
        model.append(
            button(
                "Refresh local dependency checks",
                lambda: self.dependencies_status.set_text(dependency_status()),
            )
        )
        self.model_path = entry(model, "Local Vosk model directory")
        self.choose_folder = button("Choose model folder…", self.choose_model)
        model.append(self.choose_folder)
        self.model_prepare = button(
            "Prepare saved model",
            lambda: self._live_setup_action(self.controller.prepare_model),
            primary=True,
        )
        model.append(self.model_prepare)
        self.model_status = label()
        model.append(self.model_status)
        consent = section(
            parent,
            "2 · Explicit microphone consent",
            "Default off. Enabling consent permits recording only after you explicitly activate a capture control in Live mode. "
            "Hold to talk, or start and stop with separate taps. The configured duration cap ends either mode.",
        )
        self.mic_consent = checkbox(
            label="I allow microphone capture after I explicitly start it"
        )
        consent.append(self.mic_consent)
        self.capture_sharing_status = label(
            "PipeWire may share this microphone with other apps. Pause other voice/dictation apps to avoid duplicate capture; check your desktop microphone indicator when available."
        )
        consent.append(self.capture_sharing_status)
        self.focus_delay = Gtk.SpinButton.new_with_range(2, 10, 1)
        consent.append(label("Destination selection countdown (2–10 seconds)"))
        self.focus_delay.update_property(
            [Gtk.AccessibleProperty.LABEL], ["Destination selection countdown seconds"]
        )
        consent.append(self.focus_delay)
        self.capture_limit = Gtk.SpinButton.new_with_range(5, 60, 1)
        consent.append(label("Maximum held capture (5–60 seconds)"))
        self.capture_limit.update_property(
            [Gtk.AccessibleProperty.LABEL], ["Maximum held capture seconds"]
        )
        consent.append(self.capture_limit)
        self.review_lifetime = Gtk.SpinButton.new_with_range(10, 120, 1)
        consent.append(label("Review expires after (10–120 seconds)"))
        self.review_lifetime.update_property(
            [Gtk.AccessibleProperty.LABEL], ["Review expires after seconds"]
        )
        consent.append(self.review_lifetime)
        consent.append(label("Appearance"))
        self.theme = Gtk.DropDown.new_from_strings(["System", "Light", "Dark"])
        self.theme.update_property(
            [Gtk.AccessibleProperty.LABEL], ["Appearance: System, Light or Dark"]
        )
        consent.append(self.theme)
        self.save_settings = button(
            "Save settings and revoke live grants", self.persist_settings, primary=True
        )
        self.reset_settings = button(
            "Reset settings and delete all custom shortcuts", self.reset_preferences
        )
        consent.append(self.save_settings)
        consent.append(self.reset_settings)
        self.settings_status = label()
        consent.append(self.settings_status)
        access = section(
            parent,
            "3 · Desktop keyboard permission",
            "In Live mode, connect explicitly and approve the desktop portal. "
            "Capability support does not mean permission has been granted. "
            "Keyboard input goes to the currently focused app; pause other voice-control tools before confirming to avoid competing input. "
            "Stop, mode switches and settings changes close the live sessions.",
        )
        self.connect_button = button(
            "Request desktop keyboard access…",
            lambda: self._live_setup_action(self.controller.connect),
        )
        access.append(self.connect_button)
        self.revoke_button = button(
            "Revoke desktop and shortcut access", self.stop_action
        )
        access.append(self.revoke_button)
        self.permission_status = label()
        access.append(self.permission_status)
        shortcuts = section(
            parent,
            "Optional global shortcuts",
            "Bind only when wanted. Hold-to-talk records on press and releases on key-up. "
            "Confirm acts on release in the chosen destination; high-risk stage two stays a separate UI control. "
            "Local confirmation always shows a destination selection countdown.",
        )
        self.bind_shortcuts = button(
            "Request global shortcut bindings…",
            lambda: self._live_setup_action(self.controller.connect_shortcuts),
        )
        shortcuts.append(self.bind_shortcuts)
        self.bindings_status = label()
        shortcuts.append(self.bindings_status)
        section(
            parent,
            "Private by design",
            "No cloud, network recognition, telemetry, audio files or transcript history. "
            "Only preferences and intentional custom shortcut configuration are saved. "
            "Drafts and reviewed text stay in memory and are discarded on cancel or exit. "
            "Clipboard contents are never read by the app. Optional read-back uses local espeak-ng only. "
            "Run “wayland-voice-control doctor --json” for read-only capability diagnostics. "
            "GNOME Wayland is the intended target; compositor compatibility and actual consent need real-session testing.",
        )
        self.load_settings()
        for widget, signal in (
            (self.model_path, "changed"),
            (self.mic_consent, "toggled"),
            (self.focus_delay, "value-changed"),
            (self.capture_limit, "value-changed"),
            (self.review_lifetime, "value-changed"),
            (self.theme, "notify::selected"),
        ):
            widget.connect(signal, self._setup_changed)

    def _setup_changed(self, *_):
        if self._loading_settings or self._closed:
            return
        self._settings_dirty = True
        self._pause_unsaved_setup()

    def _pause_unsaved_setup(self):
        self._held = False
        self._toggle_capture_started = False
        self.settings_status.set_text(
            "Unsaved Setup changes · live input paused. Save, prepare the model and reconnect explicitly."
        )
        # Revoke runtime microphone consent as well as all OS sessions immediately.
        # The saved preferences and the complete editable form stay unchanged until Save.
        self.controller.apply_settings(
            replace(self.controller.settings, microphone_consent=False)
        )

    def _live_setup_action(self, callback):
        if self._settings_dirty:
            self.status.set_text(
                "Unsaved Setup changes · live input paused. Save before preparing or requesting access."
            )
            return None
        if not self.controller.practice:
            return self._safe(callback)
        return None

    def _safe(self, callback):
        try:
            return callback()
        except (
            DomainError,
            SettingsError,
            OSError,
            ImportError,
            RuntimeError,
        ) as error:
            self.status.set_text(str(error))
            return None

    def _switch_mode(self, *_):
        if self._rendering:
            return
        practice = self.practice_switch.get_active()
        if practice == self.controller.practice:
            return
        self._held = False
        self._stop_reader()
        self.controller.stop()
        if self.unsubscribe:
            self.unsubscribe()
        try:
            new = self.controller_factory(practice=practice, store=self.store)
        except Exception:  # noqa: BLE001 - unavailable desktop service has safe recovery
            self._rendering = True
            self.practice_switch.set_active(True)
            self._rendering = False
            new = self.controller_factory(practice=True, store=self.store)
            self.controller = new
            self.unsubscribe = new.subscribe(self.render)
            self.status.set_text(
                "Live desktop connection unavailable. Check the session bus and run doctor; Practice is available."
            )
            return
        self.controller = new
        self.controller.set_mode(
            Mode.COMMANDS if self.command_mode.get_active() else Mode.DICTATION
        )
        self.unsubscribe = new.subscribe(self.render)
        if self._settings_dirty:
            self._pause_unsaved_setup()
        else:
            self.load_settings()

    def _command_changed(self, *_):
        self._held = False
        self.controller.set_mode(
            Mode.COMMANDS if self.command_mode.get_active() else Mode.DICTATION
        )

    def review_practice(self):
        self._safe(
            lambda: self.controller.review_text(
                self.practice_entry.get_text(), self.controller.mode
            )
        )

    def hold_begin(self):
        if (
            not self._settings_dirty
            and not self._hold_pressed
            and can_capture(self.controller.snapshot)
        ):
            self._hold_pressed = True
            self._held = True
            if not self.controller.start_recording():
                self._held = False
            self.render(self.controller.snapshot)

    def hold_end(self):
        self._hold_pressed = False
        if self._held:
            self._held = False
            self.controller.finish_recording()
        self.render(self.controller.snapshot)

    def toggle_capture_action(self):
        """Start once and tap again to finish, for users who cannot hold a control."""
        snapshot = self.controller.snapshot
        if self._settings_dirty or snapshot.practice:
            return
        if snapshot.state is State.IDLE:
            if can_capture(snapshot):
                self._stop_reader()
                self._toggle_capture_started = bool(
                    self.controller.start_recording()
                )
        elif snapshot.state is State.RECORDING:
            self._held = False
            self._toggle_capture_started = False
            if snapshot.microphone_activity == "recording":
                self.controller.finish_recording()
            else:
                # A second activation while the recorder is starting cancels it;
                # it must not create a short or unexpected capture after the tap.
                self.controller.cancel()

    def _cancel_hold(self):
        if self._held:
            self._hold_pressed = False
            self._held = False
            self.controller.cancel()

    def _hold_key(self, _keys, keyval, _code, _modifiers):
        if keyval in (Gdk.KEY_space, Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            self.hold_begin()
            return True
        return False

    def _window_key_release(self, _keys, keyval, _code, _modifiers):
        if self._hold_pressed and keyval in (
            Gdk.KEY_space,
            Gdk.KEY_Return,
            Gdk.KEY_KP_Enter,
        ):
            self.hold_end()

    def _window_key(self, _keys, keyval, _code, _modifiers):
        if keyval == Gdk.KEY_Escape:
            self.cancel_action()
            return True
        return False

    def _hold_focus_changed(self, *_):
        if not self.hold_button.has_focus():
            self._cancel_hold()

    def _active_changed(self, *_):
        if not self.is_active():
            self._cancel_hold()
            if self._toggle_capture_started:
                self._toggle_capture_started = False
                self.controller.cancel()
            # Key-up may go to another top-level window. Abandon this window's
            # physical press ownership even if a duration cap already ended capture.
            self._hold_pressed = False
            self.render(self.controller.snapshot)

    def begin_edit(self):
        identity = self._reviewed_id
        if identity and self.controller.begin_edit(identity):
            # begin_edit synchronously invalidates approval BEFORE enabling edits.
            self.editor.set_editable(True)
            self.editor.set_cursor_visible(True)
            self.editor.grab_focus()

    def finish_edit(self):
        token = self.controller.snapshot.edit_token
        if token:
            buffer = self.editor.get_buffer()
            self.controller.finish_edit(
                token,
                buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), True),
            )

    def confirm(self):
        if self._reviewed_id:
            self.controller.confirm(self._reviewed_id)

    def confirm_second(self):
        if self._reviewed_id:
            self.controller.confirm_second(self._reviewed_id)

    def cancel_action(self):
        self._held = False
        self._stop_reader()
        self.controller.cancel()

    def stop_action(self):
        self._held = False
        self._stop_reader()
        self.controller.stop()

    def load_settings(self):
        settings = self.controller.settings
        self._loading_settings = True
        try:
            self.model_path.set_text(settings.model_path)
            self.mic_consent.set_active(settings.microphone_consent)
            self.focus_delay.set_value(settings.focus_delay_seconds)
            self.capture_limit.set_value(settings.capture_limit_seconds)
            self.review_lifetime.set_value(settings.confirmation_ttl_seconds)
            self.theme.set_selected(["system", "light", "dark"].index(settings.theme))
            self._apply_theme(settings.theme)
            self._settings_dirty = False
        finally:
            self._loading_settings = False
        if self.unsubscribe:
            self.render(self.controller.snapshot)

    def _apply_theme(self, theme):
        Adw.StyleManager.get_default().set_color_scheme(
            {
                "system": Adw.ColorScheme.DEFAULT,
                "light": Adw.ColorScheme.FORCE_LIGHT,
                "dark": Adw.ColorScheme.FORCE_DARK,
            }[theme]
        )

    def persist_settings(self):
        try:
            self._held = False
            self.controller.update_settings(
                {
                    "model_path": self.model_path.get_text(),
                    "microphone_consent": self.mic_consent.get_active(),
                    "focus_delay_seconds": self.focus_delay.get_value(),
                    "capture_limit_seconds": self.capture_limit.get_value(),
                    "confirmation_ttl_seconds": self.review_lifetime.get_value(),
                    "theme": ["system", "light", "dark"][self.theme.get_selected()],
                }
            )
        except (SettingsError, OSError) as error:
            self.settings_status.set_text(str(error))
        else:
            self.load_settings()
            self.settings_status.set_text(
                "Saved. Prepare the saved model and reconnect explicitly in Live mode."
            )

    def reset_preferences(self):
        try:
            self._held = False
            self.controller.reset_settings()
        except (SettingsError, OSError) as error:
            self.settings_status.set_text(str(error))
        else:
            self.load_settings()
            self.new_custom()
            self.settings_status.set_text(
                "Defaults restored; microphone consent is off and custom shortcuts are deleted."
            )

    def choose_model(self):
        self._chooser = Gtk.FileChooserNative.new(
            "Choose local Vosk model directory",
            self,
            Gtk.FileChooserAction.SELECT_FOLDER,
            "Choose folder",
            "Cancel",
        )
        self._chooser.connect("response", self._folder_response)
        self._chooser.show()

    def _folder_response(self, chooser, response):
        if response == Gtk.ResponseType.ACCEPT:
            chosen = chooser.get_file()
            path = chosen.get_path() if chosen else None
            if path:
                self.model_path.set_text(path)
                self.settings_status.set_text(
                    "Folder selected. Save settings, then prepare the model."
                )
            else:
                self.settings_status.set_text("Choose an existing local directory.")
        chooser.destroy()
        self._chooser = None

    def _custom_item(self):
        return CustomShortcut(
            self._custom_id or uuid4().hex,
            self.custom_phrase.get_text(),
            self.custom_chord.get_text(),
            self.custom_description.get_text(),
            self.custom_enabled.get_active(),
        )

    def preview_custom(self):
        try:
            item = self._custom_item()
        except DomainError as error:
            self.custom_preview.set_text(str(error))
        else:
            self.custom_preview.set_text(
                f"Exact preview: “{item.phrase}” → {item.key_chord}\nHigh risk · two separate confirmations required."
            )

    def new_custom(self):
        self._custom_id = None
        self.custom_phrase.set_text("")
        self.custom_chord.set_text("")
        self.custom_description.set_text("")
        self.custom_enabled.set_active(True)
        self.custom_delete.set_sensitive(False)
        self.custom_error.set_text("")
        self.preview_custom()

    def load_custom(self, item):
        self._custom_id = item.id
        self.custom_phrase.set_text(item.phrase)
        self.custom_chord.set_text(item.key_chord)
        self.custom_description.set_text(item.description)
        self.custom_enabled.set_active(item.enabled)
        self.custom_delete.set_sensitive(True)
        self.custom_error.set_text("")
        self.preview_custom()

    def save_custom(self):
        try:
            item = self._custom_item()
            proposed = tuple(
                entry
                for entry in self.controller.snapshot.custom_shortcuts
                if entry.id != self._custom_id
            )
            command_catalogue((*proposed, item))
            if self._custom_id:
                self.controller.update_custom_shortcut(item)
            else:
                self.controller.add_custom_shortcut(item)
        except (DomainError, SettingsError, OSError) as error:
            self.custom_error.set_text(str(error))
        else:
            self.load_custom(item)
            self.custom_error.set_text(
                "Saved configuration. Review a new action to use it."
            )

    def delete_custom(self):
        if self._custom_id:
            try:
                self.controller.delete_custom_shortcut(self._custom_id)
            except (DomainError, SettingsError, OSError) as error:
                self.custom_error.set_text(str(error))
            else:
                self.new_custom()

    def _fill_commands(self):
        if not hasattr(self, "command_list"):
            return
        while child := self.command_list.get_first_child():
            self.command_list.remove(child)
        snapshot = self.controller.snapshot
        query = self.command_search.get_text().casefold()
        entries = list(snapshot.commands.values())
        enabled_ids = {item.id for item in entries}
        entries.extend(
            item for item in snapshot.custom_shortcuts if item.id not in enabled_ids
        )
        found = False
        for item in entries:
            text = f"{item.phrase} → {item.key_chord}\n{item.description or 'No description supplied.'}"
            custom = isinstance(item, CustomShortcut) or item.custom
            text += (
                "\nHigh risk · custom · two confirmations"
                if custom
                else f"\n{item.risk.value.capitalize()} risk"
            )
            if not getattr(item, "enabled", True):
                text += " · Disabled"
            if query not in text.casefold():
                continue
            found = True
            row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            row.append(label(text))
            if custom:
                configured = next(
                    entry for entry in snapshot.custom_shortcuts if entry.id == item.id
                )
                row.append(
                    button(
                        "Edit “" + item.phrase + "”",
                        lambda item=configured: self.load_custom(item),
                    )
                )
            if snapshot.practice and getattr(item, "enabled", True):
                row.append(
                    button(
                        "Practice “" + item.phrase + "”",
                        lambda item=item: self.try_command(item.phrase),
                    )
                )
            self.command_list.append(row)
            self.command_list.append(Gtk.Separator())
        if not found:
            self.command_list.append(label("No matching exact phrases."))

    def try_command(self, phrase):
        if self.controller.practice:
            self.command_mode.set_active(True)
            self.practice_entry.set_text(phrase)
            self.review_practice()
            self.stack.set_visible_child_name("voice")

    def read_back(self):
        action = self.controller.snapshot.pending
        if not action or action.id != self._reviewed_id:
            return
        executable = shutil.which("espeak-ng")
        if not executable:
            self.status.set_text(
                "Optional read-back unavailable. Install espeak-ng to enable local speech."
            )
            return
        self._stop_reader()
        generation = self._reader_generation
        text = action_details(action)
        # No text in command arguments, environment, shell or temporary files.
        try:
            process = subprocess.Popen(
                [executable, "--stdin"],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                shell=False,
            )
        except OSError:
            self.status.set_text(
                "Local read-back could not start. Check the espeak-ng installation."
            )
            return
        self._reader = process
        self._reader_action_id = action.id

        def run():
            try:
                process.communicate(text.encode("utf-8"), timeout=60)
            except (OSError, subprocess.TimeoutExpired):
                process.kill()
                process.communicate()
            from .gio_transport import dispatch

            def done():
                if generation == self._reader_generation and not self._closed:
                    self._reader = None

            dispatch(done)

        threading.Thread(target=run, daemon=True).start()

    def _stop_reader(self):
        self._reader_generation += 1
        self._reader_action_id = None
        if self._reader:
            try:
                self._reader.terminate()
            except ProcessLookupError:
                pass
            self._reader = None

    def render(self, snapshot):
        if self._closed:
            return
        if self._reader and (
            snapshot.pending is None
            or snapshot.pending.id != self._reader_action_id
            or snapshot.state
            not in (State.REVIEWING, State.AWAITING_SECOND_CONFIRMATION)
        ):
            self._stop_reader()
        self._rendering = True
        try:
            self.mode_status.set_text(
                "Practice · microphone off · desktop input simulated only"
                if snapshot.practice
                else "Live · explicit recording and reviewed desktop input"
            )
            status_text = (
                "Unsaved Setup changes · live input paused. Save before preparing or reconnecting."
                if self._settings_dirty
                else f"{snapshot.state.value.replace('_', ' ').capitalize()} · {snapshot.status}"
            )
            self.status.set_text(status_text)
            status_key = (
                status_text,
                snapshot.state,
                snapshot.pending.id if snapshot.pending else None,
            )
            if status_key != self._last_announced_status:
                self._last_announced_status = status_key
                announce = getattr(self.status, "announce", None)
                if callable(announce):
                    try:
                        announce(
                            status_text, Gtk.AccessibleAnnouncementPriority.MEDIUM
                        )
                    except (TypeError, RuntimeError):
                        # Older GTK versions and inactive AT bridges may not
                        # implement announcements; the status role/text remain.
                        pass
            self.readiness.set_text(
                f"Model: {snapshot.model_readiness} · Microphone consent: {'on' if snapshot.microphone_consent else 'off'} · "
                f"Keyboard grant: {'simulated' if snapshot.practice else ('granted' if snapshot.permission_granted else 'not granted')}\n"
                "Live recording needs a ready prepared model, consent and a keyboard grant."
            )
            self.model_status.set_text("Model preparation: " + snapshot.model_readiness)
            self.permission_status.set_text(
                "Practice has no desktop session."
                if snapshot.practice
                else (
                    "Keyboard permission granted for this session."
                    if snapshot.permission_granted
                    else "Keyboard permission not granted. Portal capability alone is not permission."
                )
            )
            binding_names = {
                "hold_to_talk": "Hold to talk",
                "confirm": "Confirm reviewed action",
                "cancel": "Cancel action",
            }
            binding_header = (
                "Granted bindings and local fallbacks:"
                if snapshot.shortcut_bindings
                else "No granted global bindings. Local controls remain available:"
            )
            self.bindings_status.set_text(
                "\n".join(
                    [
                        binding_header,
                        *(
                            f"{label}: {snapshot.shortcut_bindings.get(name, 'Not bound; use local control')}"
                            for name, label in binding_names.items()
                        ),
                    ]
                )
            )
            if snapshot.state is not State.RECORDING:
                self._held = False
                self._toggle_capture_started = False
            self.hold_button.set_sensitive(
                not self._settings_dirty
                and (can_capture(snapshot) or self._hold_pressed)
            )
            self.hold_button.set_label(
                {
                    "loading": "Preparing capture · release to cancel",
                    "recording": "Recording · release to finish",
                    "processing": "Processing locally · microphone off",
                    "idle": "Hold to talk · Space while focused",
                }[snapshot.microphone_activity]
            )
            self.toggle_capture_button.set_visible(not snapshot.practice)
            toggle_label = {
                State.IDLE: "Start recording without holding",
                State.RECORDING: (
                    "Cancel starting recording"
                    if snapshot.microphone_activity == "loading"
                    else "Stop recording and review"
                ),
                State.PROCESSING: "Finishing recording",
            }.get(snapshot.state, "Start recording without holding")
            self.toggle_capture_button.set_label(toggle_label)
            self.toggle_capture_button.update_property(
                [Gtk.AccessibleProperty.LABEL], [toggle_label]
            )
            self.toggle_capture_button.set_sensitive(
                not self._settings_dirty
                and not snapshot.practice
                and (can_capture(snapshot) or snapshot.state is State.RECORDING)
            )
            self.practice_box.set_visible(snapshot.practice)
            for widget in (
                self.connect_button,
                self.bind_shortcuts,
                self.model_prepare,
            ):
                widget.set_sensitive(not snapshot.practice and not self._settings_dirty)
            self.draft.set_text(snapshot.draft_text)
            editing = snapshot.state is State.EDITING
            action = snapshot.pending
            self._reviewed_id = action.id if action else None
            if not editing:
                self.editor.set_editable(False)
                self.editor.set_cursor_visible(False)
                self.editor.get_buffer().set_text(
                    action.payload
                    if action and action.kind.value == "text"
                    else (action.phrase if action else "")
                )
            self.review_details.set_text(
                "Editing · approval revoked. Re-review the complete buffer."
                if editing
                else action_details(action)
            )
            self.edit_button.set_sensitive(
                action is not None
                and snapshot.state
                in (State.REVIEWING, State.AWAITING_SECOND_CONFIRMATION, State.ARMED)
            )
            self.rereview_button.set_visible(editing)
            self.confirm_button.set_sensitive(
                action is not None and snapshot.state is State.REVIEWING
            )
            self.second_button.set_visible(
                snapshot.state is State.AWAITING_SECOND_CONFIRMATION
            )
            self.second_button.set_sensitive(
                snapshot.state is State.AWAITING_SECOND_CONFIRMATION
            )
            self.countdown.set_text(
                f"Choose the destination field now. Sending in {math.ceil(snapshot.countdown_seconds)} seconds. Stop or Escape cancels."
                if snapshot.state is State.ARMED
                else ""
            )
            self.readback_button.set_sensitive(
                action is not None
                and snapshot.state
                in (State.REVIEWING, State.AWAITING_SECOND_CONFIRMATION)
            )
            self.practice_output.set_visible(snapshot.practice)
            if snapshot.practice:
                self.practice_output.set_text(
                    "Practice output · simulated only:\n"
                    + action_details(snapshot.practice_last_action)
                    if snapshot.practice_last_action
                    else "Practice output: no simulated action yet."
                )
            signature = (
                tuple(snapshot.commands.items()),
                snapshot.custom_shortcuts,
                snapshot.practice,
            )
            if signature != self._catalogue_signature:
                self._catalogue_signature = signature
                self._fill_commands()
        finally:
            self._rendering = False

    def shutdown(self):
        if self._closed:
            return
        self._closed = True
        self._held = False
        self._stop_reader()
        if self.unsubscribe:
            self.unsubscribe()
        self.controller.stop()
        if self._chooser:
            self._chooser.destroy()
            self._chooser = None

    def _close(self, *_):
        self.shutdown()
        return False
