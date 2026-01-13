import sys
import json
import queue
import threading
import webbrowser
import tkinter as tk
import urllib.request
from pathlib import Path
from data import (
    DEBUG,
    CURRENT_VERSION,
    RELEASE_API_ENDPOINT,
    DOCUMENTATION_URL,
    DEFAULT_ANIMATION_DURATION,
    read_json_file,
    write_json_file,
)
from wan_files import CHUNK_SIZES
from icons.data import (
    SMALL_ICON_DATA,
    LARGE_ICON_DATA,
)
from PIL import Image, ImageTk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from generators import (
    generate_sprite_main,
    validate_sg_input_folder,
    generate_frames_main,
    wan_transform_main,
    validate_external_input,
    BASE_SPRITE_INFO,
)


def validate_integer_input(new_value):
    if new_value == "" or new_value == "-":
        return True
    try:
        value = int(new_value)
        return -999999 <= value <= 999999
    except ValueError:
        return False


# Constants for animation playback
MS_PER_TICK = 1000 / 60

# Category to visible checkboxes mapping
from generators.constants import SPRITE_CATEGORY_CONFIGS


def _build_category_checkbox_map():
    """Build checkbox map from SPRITE_CATEGORY_CONFIGS.

    If a config value is None, the corresponding checkbox is shown.
    """
    checkbox_map = {}
    checkbox_keys = ["tiles_mode", "used_base_palette"]
    for category_key, config in SPRITE_CATEGORY_CONFIGS.items():
        # Convert snake_case to display name (e.g., "4bpp_standalone" -> "4bpp Standalone")
        parts = category_key.split("_")
        display_name = parts[0] + " " + parts[1].title() if len(parts) > 1 else parts[0]
        checkboxes = [key for key in checkbox_keys if config.get(key) is None]
        checkbox_map[display_name] = checkboxes
    return checkbox_map


CATEGORY_CHECKBOX_MAP = _build_category_checkbox_map()


class AnimationPlayer:
    """Mixin class providing shared animation playback functionality.

    Requires subclass to define:
        - self.current_sequence: list of (frame_num, duration_ms, image) tuples
        - self.current_frame_index: int
        - self.is_playing: bool
        - self.playback_after_id: after ID or None
        - self.is_dark_background: bool
        - self.should_loop: tk.BooleanVar
        - self.image_label: tk.Label for displaying frames
        - self.play_button: ttk.Button for play/stop
        - self.frame_spinbox_var: tk.StringVar for current frame display
        - self._get_after_widget(): method returning widget to call after() on
    """

    def _init_playback_state(self):
        """Initialize playback state variables."""
        self.current_sequence = []
        self.current_frame_index = 0
        self.is_playing = False
        self.playback_after_id = None
        self.is_dark_background = True

    def _get_after_widget(self):
        """Return the widget to use for after() calls. Override in subclass."""
        raise NotImplementedError("Subclass must implement _get_after_widget()")

    def _toggle_playback(self):
        """Toggle between playing and stopped state."""
        if self.is_playing:
            self._stop_playback()
        else:
            self._start_playback()

    def _start_playback(self):
        """Start animation playback."""
        if self.is_playing or not self.current_sequence:
            return

        # Reset to start if at end and not looping
        if (
            not self.should_loop.get()
            and self.current_frame_index >= len(self.current_sequence) - 1
        ):
            self.current_frame_index = 0

        self.is_playing = True
        self.play_button.config(text="Stop")
        self._advance_frame()

    def _stop_playback(self):
        """Stop animation playback."""
        if self.playback_after_id is not None:
            try:
                self._get_after_widget().after_cancel(self.playback_after_id)
            except Exception:
                pass
            self.playback_after_id = None

        self.is_playing = False
        if self.play_button:
            self.play_button.config(text="Play")

    def _reset_playback(self):
        """Reset playback state."""
        self._stop_playback()
        self.current_frame_index = 0

    def _advance_frame(self):
        """Advance to next frame in animation."""
        if not self.is_playing or not self.current_sequence:
            return

        # Ensure index is within bounds
        if self.current_frame_index >= len(self.current_sequence):
            self.current_frame_index = 0

        frame_num, duration_ms, image = self.current_sequence[self.current_frame_index]
        self.image_label.config(image=image)
        self.frame_spinbox_var.set(str(frame_num))

        next_index = self.current_frame_index + 1
        if next_index >= len(self.current_sequence):
            if self.should_loop.get():
                self.current_frame_index = 0
                self.playback_after_id = self._get_after_widget().after(
                    duration_ms, self._advance_frame
                )
            else:
                self._stop_playback()
        else:
            self.current_frame_index = next_index
            self.playback_after_id = self._get_after_widget().after(
                duration_ms, self._advance_frame
            )

    def _toggle_background(self):
        """Toggle between dark and light background."""
        self.is_dark_background = not self.is_dark_background
        bg_color = "black" if self.is_dark_background else "white"
        self.image_label.config(bg=bg_color)


class InfoDialog:
    """About dialog showing version, documentation links, and update checker."""

    def __init__(self, parent):
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("About")
        self.dialog.geometry("400x330")
        self.dialog.resizable(False, False)
        self.dialog.transient(parent)
        self.dialog.grab_set()
        self.dialog.focus_set()
        self._build_ui()

    def _build_ui(self):
        main_frame = ttk.Frame(self.dialog)
        main_frame.pack(fill=tk.BOTH, expand=True)

        header_frame = tk.Frame(main_frame, bg="#2c3e50", height=80)
        header_frame.pack(fill=tk.X)
        header_frame.pack_propagate(False)

        tk.Label(
            header_frame,
            text="Wanimation Studio",
            font=("Arial", 16, "bold"),
            bg="#2c3e50",
            fg="white",
        ).pack(pady=(20, 5))

        tk.Label(
            header_frame,
            text=f"Version {CURRENT_VERSION}",
            font=("Arial", 9),
            bg="#2c3e50",
            fg="#ecf0f1",
        ).pack()

        content_frame = ttk.Frame(main_frame, padding=30)
        content_frame.pack(fill=tk.BOTH, expand=True)

        desc_label = tk.Label(
            content_frame,
            text="A tool for Explorers of Sky that converts\nframes into sprites and sprites back to frames",
            font=("Arial", 10),
            justify=tk.CENTER,
            wraplength=340,
        )
        desc_label.pack(pady=(0, 15))

        separator = ttk.Separator(content_frame, orient=tk.HORIZONTAL)
        separator.pack(fill=tk.X, pady=10)

        ttk.Label(
            content_frame,
            text="Built by WraithFire",
            font=("Arial", 9, "italic"),
            justify=tk.CENTER,
        ).pack(pady=(0, 20))

        button_frame = ttk.Frame(content_frame)
        button_frame.pack(fill=tk.X, pady=(0, 10))

        style = ttk.Style()
        style.configure("Accent.TButton", font=("Arial", 10))

        ttk.Button(
            button_frame,
            text="View Docs",
            command=lambda: webbrowser.open(DOCUMENTATION_URL),
            style="Accent.TButton",
        ).pack(fill=tk.X, pady=(0, 10))

        ttk.Button(button_frame, text="Close", command=self.dialog.destroy).pack(
            fill=tk.X
        )


class AnimationViewer(AnimationPlayer):
    """Popup window for previewing sprite animations with playback controls."""

    def __init__(self, parent, title, frame_number_to_image, animation_group):
        self.frame_number_to_image = frame_number_to_image
        self.animation_group = animation_group

        self._init_state()
        self._create_window(parent, title)
        self._create_ui()
        self._on_animation_changed()
        self.window.wait_window()

    def _init_state(self):
        self.window = None
        self.image_label = None
        self.play_button = None
        self.frame_spinbox = None

        self.current_anim_index = tk.IntVar(value=1)
        self.frame_spinbox_var = tk.StringVar(value="0")
        self.should_loop = tk.BooleanVar(value=True)
        self._frame_num_to_index = {}

        # Initialize playback state from mixin
        self._init_playback_state()

    def _get_after_widget(self):
        """Return widget to use for after() calls."""
        return self.window

    def _create_window(self, parent, title):
        self.window = tk.Toplevel(parent)
        self.window.title(title)
        self.window.geometry("700x600")
        self.window.transient(parent)
        self.window.grab_set()
        self.window.focus_set()

    def _create_ui(self):
        control_frame = ttk.Frame(self.window, padding=8)
        control_frame.pack(side=tk.TOP, fill=tk.X)

        self._create_animation_selector(control_frame)
        self._create_playback_controls(control_frame)
        self._create_frame_selector(control_frame)

        self.image_label = tk.Label(self.window, bg="black")
        self.image_label.pack(expand=True, fill=tk.BOTH)

    def _create_animation_selector(self, parent):
        ttk.Label(parent, text="Animation:").pack(side=tk.LEFT)

        max_animations = max(1, len(self.animation_group))
        ttk.Spinbox(
            parent,
            from_=1,
            to=max_animations,
            textvariable=self.current_anim_index,
            width=6,
            state="readonly",
            command=self._on_animation_changed,
        ).pack(side=tk.LEFT, padx=(6, 12))

    def _create_playback_controls(self, parent):
        ttk.Checkbutton(parent, text="Loop", variable=self.should_loop).pack(
            side=tk.LEFT, padx=4
        )

        self.play_button = ttk.Button(
            parent, text="Play", command=self._toggle_playback
        )
        self.play_button.pack(side=tk.LEFT, padx=4)

        ttk.Button(parent, text="Toggle BG", command=self._toggle_background).pack(
            side=tk.LEFT, padx=4
        )

    def _create_frame_selector(self, parent):
        self.frame_spinbox = ttk.Spinbox(
            parent,
            textvariable=self.frame_spinbox_var,
            width=8,
            state="readonly",
            command=self._on_frame_selected,
        )
        self.frame_spinbox.pack(side=tk.RIGHT)

        ttk.Label(parent, text="Frame:").pack(side=tk.RIGHT, padx=(12, 4))

    # === Animation Loading ===

    def _on_animation_changed(self):
        anim_index = int(self.current_anim_index.get()) - 1

        if not (0 <= anim_index < len(self.animation_group)):
            self.current_sequence = []
            self._frame_num_to_index = {}
            self._reset_playback()
            return

        self._load_animation(anim_index)
        self._reset_playback()
        self._update_frame_selector()

    def _load_animation(self, anim_index):
        animation = self.animation_group[anim_index]
        self.current_sequence = []
        self._frame_num_to_index = {}

        for frame_data in animation:
            frame_num = frame_data["frame"]

            image = self.frame_number_to_image.get(frame_num)
            if image is not None:
                duration_ticks = frame_data.get("duration")
                duration_ms = int(duration_ticks * MS_PER_TICK)

                idx = len(self.current_sequence)
                self.current_sequence.append((frame_num, duration_ms, image))
                self._frame_num_to_index[frame_num] = idx

    def _update_frame_selector(self):
        if self.current_sequence:
            frame_numbers = [
                str(frame_num) for frame_num, _, _ in self.current_sequence
            ]
            self.frame_spinbox.config(values=frame_numbers)
            self.frame_spinbox_var.set(frame_numbers[0])
            _, _, image = self.current_sequence[0]
            self.image_label.config(image=image)
        else:
            self.frame_spinbox.config(values=[])
            self.frame_spinbox_var.set("0")
            self.image_label.config(image="")

    # === Frame Display ===

    def _on_frame_selected(self):
        if self.is_playing:
            self._stop_playback()

        if not self.current_sequence:
            return

        try:
            selected_frame_num = int(self.frame_spinbox_var.get())
        except ValueError:
            return

        idx = self._frame_num_to_index.get(selected_frame_num)
        if idx is not None:
            self.current_frame_index = idx
            _, _, image = self.current_sequence[idx]
            self.image_label.config(image=image)


class AnimationEditorDialog(AnimationPlayer):
    """Dialog for editing animation sequences with live preview."""

    def __init__(
        self, parent, title, initial_data=None, available_frames=None, frame_images=None
    ):
        self.result = None
        self.available_frames = available_frames or ()
        self.frame_images = frame_images or {}
        self.frame_entries = []  # List of (frame_var, duration_var, row_frame)
        self.selected_rows = set()  # Set of selected row_frame widgets
        self.base_title = title
        self.made_changes = False

        # Initialize UI references before mixin state
        self.image_label = None
        self.play_button = None
        self.frame_spinbox = None
        self.frame_spinbox_var = tk.StringVar(value="0")
        self.should_loop = tk.BooleanVar(value=True)

        # Initialize playback state from mixin
        self._init_playback_state()

        self._build_window(parent, title)
        self._build_ui()
        self.validate_integer_input = (
            self.dialog.register(validate_integer_input),
            "%P",
        )
        self._load_initial_data(initial_data)
        self._update_preview()
        self.dialog.wait_window()

    def _get_after_widget(self):
        """Return widget to use for after() calls."""
        return self.dialog

    def _build_window(self, parent, title):
        self.dialog = tk.Toplevel(parent)
        self.dialog.title(title)
        self.dialog.geometry("1000x600")
        self.dialog.transient(parent)
        self.dialog.grab_set()
        self.dialog.focus_set()
        self.dialog.protocol("WM_DELETE_WINDOW", self._on_close_attempt)

        # Keyboard shortcuts
        self.dialog.bind("<Control-a>", lambda e: self._select_all_rows())
        self.dialog.bind("<Control-A>", lambda e: self._select_all_rows())
        self.dialog.bind("<Escape>", lambda e: self._deselect_all_rows())
        self.dialog.bind("<Up>", self._on_arrow_up)
        self.dialog.bind("<Down>", self._on_arrow_down)
        self.dialog.bind("<Left>", lambda e: self._on_arrow_key(-10))
        self.dialog.bind("<Right>", lambda e: self._on_arrow_key(10))

    def _build_ui(self):
        # Create style for selected rows
        style = ttk.Style()
        style.configure("Selected.TFrame", background="#cce5ff")

        main_frame = ttk.Frame(self.dialog, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Available frames header (centered, limited display)
        header_frame = ttk.Frame(main_frame)
        header_frame.pack(fill=tk.X, pady=(0, 10))

        max_display = 30  # Max frames to show before truncating
        frames_list = list(self.available_frames)
        if len(frames_list) > max_display:
            frames_text = ", ".join(str(f) for f in frames_list[:max_display])
            remaining = len(frames_list) - max_display
            frames_text += f" ... +{remaining} more"
        else:
            frames_text = ", ".join(str(f) for f in frames_list)

        frames_label = tk.Label(
            header_frame,
            text=f"Available frames: {frames_text}",
            font=("Arial", 10),
            fg="blue",
            justify="center",
        )
        frames_label.pack(expand=True, fill=tk.X)

        # Dynamic wrap on resize
        def update_wraplength(event=None):
            frames_label.configure(wraplength=header_frame.winfo_width() - 20)

        header_frame.bind("<Configure>", update_wraplength)

        paned = tk.PanedWindow(main_frame, orient=tk.HORIZONTAL, sashwidth=10)
        paned.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        # Left pane: Frame editor
        left_frame = ttk.Frame(paned)
        paned.add(left_frame, minsize=500)
        self._create_editor_pane(left_frame)

        # Right pane: Live preview
        right_frame = ttk.Frame(paned)
        paned.add(right_frame, minsize=500)
        self._create_preview_pane(right_frame)

        # Bottom buttons (centered)
        button_frame = ttk.Frame(main_frame)
        button_frame.pack()
        ttk.Button(
            button_frame, text="Save Animation", command=self._save_and_close
        ).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=self._on_close_attempt).pack(
            side=tk.LEFT, padx=5
        )

    # === Editor Pane (Left) ===

    def _create_editor_pane(self, parent):
        # Scrollable frame list
        list_frame = ttk.LabelFrame(parent, text="Animation Frames", padding=10)
        list_frame.pack(fill=tk.BOTH, expand=True)

        canvas = tk.Canvas(list_frame, highlightthickness=0, bd=0)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=canvas.yview)
        self.scrollable_frame = ttk.Frame(canvas)

        def update_scroll_region(event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))
            if self.scrollable_frame.winfo_reqheight() > canvas.winfo_height():
                scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            else:
                scrollbar.pack_forget()

        self.scrollable_frame.bind("<Configure>", update_scroll_region)
        canvas.bind("<Configure>", update_scroll_region)

        canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    # === Preview Pane (Right) ===

    def _create_preview_pane(self, parent):
        preview_frame = ttk.LabelFrame(parent, text="Live Preview", padding=10)
        preview_frame.pack(fill=tk.BOTH, expand=True)

        # Playback controls
        control_frame = ttk.Frame(preview_frame)
        control_frame.pack(fill=tk.X, pady=5)

        ttk.Checkbutton(control_frame, text="Loop", variable=self.should_loop).pack(
            side=tk.LEFT, padx=4
        )

        self.play_button = ttk.Button(
            control_frame, text="Play", command=self._toggle_playback
        )
        self.play_button.pack(side=tk.LEFT, padx=4)

        ttk.Button(
            control_frame, text="Toggle BG", command=self._toggle_background
        ).pack(side=tk.LEFT, padx=4)

        # Frame selector (right side of controls)
        self.frame_spinbox = ttk.Spinbox(
            control_frame,
            textvariable=self.frame_spinbox_var,
            width=5,
            state="readonly",
            command=self._on_preview_frame_selected,
        )
        self.frame_spinbox.pack(side=tk.RIGHT)
        ttk.Label(control_frame, text="Frame:").pack(side=tk.RIGHT, padx=(12, 4))

        # Preview canvas
        self.image_label = tk.Label(preview_frame, bg="black")
        self.image_label.pack(expand=True, fill=tk.BOTH, pady=5)

    # === Data Loading ===

    def _load_initial_data(self, initial_data):
        if initial_data:
            for frame_data in initial_data:
                self._add_frame_row(
                    frame_no=frame_data["frame"],
                    duration=frame_data["duration"],
                    is_initial_load=True,
                )
        else:
            self._add_frame_row(is_initial_load=True)

    def _add_frame_row(
        self,
        frame_no=None,
        duration=DEFAULT_ANIMATION_DURATION,
        insert_after=None,
        is_initial_load=False,
    ):
        if frame_no is None:
            frame_no = self.available_frames[0] if self.available_frames else 0

        row_frame = tk.Frame(
            self.scrollable_frame, bd=2, relief=tk.FLAT, padx=4, pady=2
        )

        # Ctrl+Click on frame to toggle selection
        row_frame.bind(
            "<Control-Button-1>", lambda e, rf=row_frame: self._toggle_row_selection(rf)
        )

        if insert_after is not None:
            insert_index = None
            for idx, (_, _, existing_row) in enumerate(self.frame_entries):
                if existing_row == insert_after:
                    insert_index = idx + 1
                    break
            if insert_index is not None and insert_index < len(self.frame_entries):
                row_frame.pack(
                    fill=tk.X, pady=3, before=self.frame_entries[insert_index][2]
                )
            else:
                row_frame.pack(fill=tk.X, pady=3)
        else:
            row_frame.pack(fill=tk.X, pady=3)

        # Frame number input - Ctrl+Click to toggle selection
        frame_label = tk.Label(row_frame, text="Frame:")
        frame_label.pack(side=tk.LEFT, padx=(0, 4))
        frame_label.bind(
            "<Control-Button-1>", lambda e, rf=row_frame: self._toggle_row_selection(rf)
        )

        frame_var = tk.IntVar(value=frame_no)
        frame_spinbox = ttk.Spinbox(
            row_frame,
            from_=0,
            to=9999,
            textvariable=frame_var,
            width=6,
            validate="key",
            validatecommand=self.validate_integer_input,
            command=lambda: self._on_frame_changed(),
        )
        frame_spinbox.pack(side=tk.LEFT, padx=(0, 12))
        frame_spinbox.bind("<Up>", self._on_arrow_up)
        frame_spinbox.bind("<Down>", self._on_arrow_down)
        frame_spinbox.bind("<Left>", lambda e: self._on_arrow_key(-10))
        frame_spinbox.bind("<Right>", lambda e: self._on_arrow_key(10))
        frame_var.trace_add("write", lambda *args: self._on_frame_changed())

        # Duration input - Ctrl+Click to toggle selection
        duration_label = tk.Label(row_frame, text="Duration:")
        duration_label.pack(side=tk.LEFT, padx=(0, 4))
        duration_label.bind(
            "<Control-Button-1>", lambda e, rf=row_frame: self._toggle_row_selection(rf)
        )
        duration_var = tk.IntVar(value=duration)
        duration_spinbox = ttk.Spinbox(
            row_frame,
            from_=1,
            to=9999,
            textvariable=duration_var,
            width=6,
            validate="key",
            validatecommand=self.validate_integer_input,
            command=lambda: self._on_frame_changed(),
        )
        duration_spinbox.pack(side=tk.LEFT, padx=(0, 12))
        duration_spinbox.bind("<Up>", self._on_arrow_up)
        duration_spinbox.bind("<Down>", self._on_arrow_down)
        duration_spinbox.bind("<Left>", lambda e: self._on_arrow_key(-10))
        duration_spinbox.bind("<Right>", lambda e: self._on_arrow_key(10))
        duration_var.trace_add("write", lambda *args: self._on_frame_changed())

        # Add button - copy duration from this row
        ttk.Button(
            row_frame,
            text="+",
            width=3,
            command=lambda rf=row_frame, dv=duration_var: self._add_frame_row(
                insert_after=rf, duration=dv.get()
            ),
        ).pack(side=tk.LEFT, padx=2)

        # Remove button
        ttk.Button(
            row_frame,
            text="-",
            width=3,
            command=lambda rf=row_frame: self._remove_frame_row(rf),
        ).pack(side=tk.LEFT, padx=2)

        if insert_after is not None:
            insert_index = None
            for idx, (_, _, existing_row) in enumerate(self.frame_entries):
                if existing_row == insert_after:
                    insert_index = idx + 1
                    break
            if insert_index is not None:
                self.frame_entries.insert(
                    insert_index, (frame_var, duration_var, row_frame)
                )
            else:
                self.frame_entries.append((frame_var, duration_var, row_frame))
        else:
            self.frame_entries.append((frame_var, duration_var, row_frame))

        if not is_initial_load:
            self._mark_as_changed()
            self._update_preview()

    def _remove_frame_row(self, row_frame):
        if len(self.frame_entries) <= 1:
            return
        for idx, (_, _, rf) in enumerate(self.frame_entries):
            if rf == row_frame:
                self.frame_entries.pop(idx)
                self.selected_rows.discard(row_frame)
                row_frame.destroy()
                self._mark_as_changed()
                self._update_preview()
                break

    def _on_frame_changed(self):
        self._mark_as_changed()
        self._update_preview()

    def _mark_as_changed(self):
        if not self.made_changes:
            self.made_changes = True
            self.dialog.title(f"{self.base_title} *")

    # === Selection Methods ===

    def _select_all_rows(self):
        """Select all frame rows (Ctrl+A)."""
        for _, _, row_frame in self.frame_entries:
            self.selected_rows.add(row_frame)
            self._update_row_highlight(row_frame, selected=True)

    def _deselect_all_rows(self):
        """Deselect all frame rows (Escape)."""
        for row_frame in list(self.selected_rows):
            self._update_row_highlight(row_frame, selected=False)
        self.selected_rows.clear()

    def _toggle_row_selection(self, row_frame):
        """Toggle selection state of a row (click)."""
        if row_frame in self.selected_rows:
            self.selected_rows.discard(row_frame)
            self._update_row_highlight(row_frame, selected=False)
        else:
            self.selected_rows.add(row_frame)
            self._update_row_highlight(row_frame, selected=True)

    def _update_row_highlight(self, row_frame, selected):
        """Update visual highlight for a row with border."""
        try:
            if selected:
                row_frame.configure(relief=tk.GROOVE, highlightthickness=1)
            else:
                row_frame.configure(relief=tk.FLAT, highlightthickness=0)
        except tk.TclError:
            pass

    def _on_arrow_up(self, event):
        """Handle Up arrow - adjust selected durations, block native spinbox."""
        if self.selected_rows:
            self._adjust_selected_duration(1)
            return "break"  # Prevent native spinbox behavior

    def _on_arrow_down(self, event):
        """Handle Down arrow - adjust selected durations, block native spinbox."""
        if self.selected_rows:
            self._adjust_selected_duration(-1)
            return "break"  # Prevent native spinbox behavior

    def _on_arrow_key(self, delta):
        """Handle Shift+Arrow - adjust selected durations, block native spinbox."""
        if self.selected_rows:
            self._adjust_selected_duration(delta)
            return "break"  # Prevent native spinbox behavior

    def _adjust_selected_duration(self, delta):
        """Adjust duration of all selected frames by delta."""
        if not self.selected_rows:
            return
        for frame_var, duration_var, row_frame in self.frame_entries:
            if row_frame in self.selected_rows:
                try:
                    current = duration_var.get()
                    new_val = max(1, current + delta)  # Minimum duration of 1
                    duration_var.set(new_val)
                except tk.TclError:
                    pass

    # === Preview Update ===

    def _update_preview(self):
        self.current_sequence = []

        for frame_var, duration_var, _ in self.frame_entries:
            try:
                frame_num = frame_var.get()
                duration_ticks = duration_var.get()
            except tk.TclError:
                continue

            image = self.frame_images.get(frame_num)
            if image is not None:
                duration_ms = int(duration_ticks * MS_PER_TICK)
                self.current_sequence.append((frame_num, duration_ms, image))

        # Update frame spinbox values
        if self.current_sequence:
            frame_numbers = [
                str(frame_num) for frame_num, _, _ in self.current_sequence
            ]
            self.frame_spinbox.config(values=frame_numbers)
            if not self.is_playing:
                self.current_frame_index = 0
                self.frame_spinbox_var.set(frame_numbers[0])
                _, _, image = self.current_sequence[0]
                self.image_label.config(image=image)
        else:
            self.frame_spinbox.config(values=[])
            self.frame_spinbox_var.set("0")
            self.image_label.config(image="")

    def _on_preview_frame_selected(self):
        """Handle manual frame selection from spinbox."""
        if self.is_playing:
            self._stop_playback()

        if not self.current_sequence:
            return

        try:
            selected_frame_num = int(self.frame_spinbox_var.get())
        except ValueError:
            return

        # Find index of selected frame
        for idx, (frame_num, _, image) in enumerate(self.current_sequence):
            if frame_num == selected_frame_num:
                self.current_frame_index = idx
                self.image_label.config(image=image)
                break

    # === Save/Close ===

    def _on_close_attempt(self):
        self._stop_playback()
        if self.made_changes:
            response = messagebox.askyesnocancel(
                "Unsaved Changes", "Save before closing?", parent=self.dialog
            )
            if response is True:
                self._save_and_close()
            elif response is False:
                self.dialog.destroy()
        else:
            self.dialog.destroy()

    def _save_and_close(self):
        self._stop_playback()
        frame_data = []
        for frame_var, duration_var, _ in self.frame_entries:
            try:
                frame_data.append(
                    {"frame": frame_var.get(), "duration": duration_var.get()}
                )
            except tk.TclError:
                messagebox.showerror(
                    "Invalid Data",
                    "Please fill in all fields correctly.",
                    parent=self.dialog,
                )
                return

        # Validate frames
        if self.available_frames:
            invalid = [
                f["frame"]
                for f in frame_data
                if f["frame"] not in self.available_frames
            ]
            if invalid:
                messagebox.showerror(
                    "Invalid Frames",
                    f"Frames not available: {invalid}",
                    parent=self.dialog,
                )
                return

        self.result = frame_data
        self.made_changes = False
        self.dialog.destroy()


class WanimationStudioGUI:
    """Main application GUI for sprite generation, frame extraction, and WAN I/O."""

    def __init__(self, root):
        self.root = root
        self.root.title("Wanimation Studio")
        self.root.geometry("1000x680")

        small_icon = tk.PhotoImage(data=SMALL_ICON_DATA)
        large_icon = tk.PhotoImage(data=LARGE_ICON_DATA)
        self.root.iconphoto(True, small_icon, large_icon)

        # Custom style
        style = ttk.Style()
        style.configure("Large.TButton", font=("Arial", 12, "bold"), padding=10)
        style.configure("Bold.TLabelframe.Label", font=("Arial", 10, "bold"))

        # Configuration variables
        self.input_folder = tk.StringVar(value="")
        self.min_density = tk.IntVar(value=50)
        self.displace_x = tk.IntVar(value=0)
        self.displace_y = tk.IntVar(value=0)
        self.quick_select_var = tk.StringVar(value="Center")
        self.export_format = tk.StringVar(value="WAN")
        self.sprite_category = tk.StringVar(value="4bpp Standalone")
        self.use_tiles_mode = tk.BooleanVar(value=False)
        self.used_base_palette = tk.BooleanVar(value=False)
        self.animation_group = []

        # Frame images for viewer
        self.frame_number_to_image = {}

        # Sprite Generator folder data
        self.sg_images_dict = {}
        self.sg_shared_palette = None
        self.sg_max_colors_used = None
        self.sg_image_height = None
        self.sg_image_width = None
        self.sg_available_frames = []

        # Frames Generator data
        self.fg_input_display = tk.StringVar(value="")
        self.fg_base_sprite_file = tk.StringVar(value="")  # Optional base sprite path
        self.fg_sprite = None
        self.fg_base_sprite = None  # Optional base sprite for shared palette
        self.fg_input_path = None  # Path object for folder or WAN file
        self.fg_validation_info = {}  # validation info from sprite.validate()
        self.fg_base_validation_info = {}  # validation info from sprite.validate()

        # Wan IO data
        self.wan_io_folder = tk.StringVar(value="")
        self.wan_io_wan_file = tk.StringVar(value="")
        self.wan_io_input_path = None  # Path object for folder or WAN file
        self.wan_io_is_folder = False  # True if folder selected, False if WAN file
        self.wan_io_sprite = None  # Validated sprite object

        self.validate_integer_input = (self.root.register(validate_integer_input), "%P")

        # Thread-safe stdout queue
        self.stdout_queue = queue.Queue(maxsize=1000)
        self._stdout_processor_scheduled = threading.Event()

        self.create_widgets()
        self.redirect_stdout_to_console()
        self.root.after(100, self.check_for_update)

    def create_widgets(self):
        paned_window = tk.PanedWindow(self.root, orient=tk.HORIZONTAL, sashwidth=10)
        paned_window.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # LEFT COLUMN
        left_frame = ttk.Frame(paned_window)
        paned_window.add(left_frame, minsize=500)

        self.notebook = ttk.Notebook(left_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)
        self.notebook.bind("<<NotebookTabChanged>>", self.clear_console)

        # Tab 1
        sprite_generator_tab = ttk.Frame(self.notebook, padding=(10, 0))
        self.notebook.add(sprite_generator_tab, text="Sprite Generator")
        sprite_generator_tab.columnconfigure(0, weight=1)
        sprite_generator_tab.rowconfigure(3, weight=1)
        self.create_sprite_generator_tab(sprite_generator_tab)

        # Tab 2
        frames_generator_tab = ttk.Frame(self.notebook, padding=(10, 0))
        self.notebook.add(frames_generator_tab, text="Frames Generator")
        self.create_frames_generator_tab(frames_generator_tab)

        # Tab 3
        wan_io_tab = ttk.Frame(self.notebook, padding=(10, 0))
        self.notebook.add(wan_io_tab, text="Wan IO")
        self.create_wan_io_tab(wan_io_tab)

        # RIGHT COLUMN
        right_frame = ttk.Frame(paned_window)
        paned_window.add(right_frame, minsize=500)

        info_btn = ttk.Button(
            right_frame, text="About", command=lambda: InfoDialog(self.root)
        )
        info_btn.pack(anchor=tk.E, padx=(0, 17), pady=(0, 17))

        console_container = ttk.Frame(right_frame)
        console_container.pack(fill=tk.BOTH, expand=True)
        self.create_console(console_container)

    def create_sprite_generator_tab(self, parent):
        # Config buttons
        config_frame = ttk.LabelFrame(
            parent, text="Configuration", style="Bold.TLabelframe", padding=10
        )
        config_frame.grid(row=0, column=0, sticky="ew", pady=(15, 0))
        config_frame.columnconfigure(0, weight=1)
        config_frame.columnconfigure(1, weight=1)

        self.load_config_btn = ttk.Button(
            config_frame, text="Load Config", command=self.load_config
        )
        self.load_config_btn.grid(row=0, column=0, sticky="ew", padx=(0, 2))

        ttk.Button(config_frame, text="Save Config", command=self.save_config).grid(
            row=0, column=1, sticky="ew", padx=(2, 0)
        )

        # Basic Settings
        basic_frame = ttk.LabelFrame(
            parent, text="Basic Settings", style="Bold.TLabelframe", padding=(10, 5)
        )
        basic_frame.grid(row=1, column=0, sticky="ew", pady=10)
        basic_frame.columnconfigure(1, weight=1)
        self.create_basic_settings(basic_frame)

        # Runtime Options - Collapsible LabelFrame
        runtime_container = ttk.Frame(parent)
        runtime_container.grid(row=2, column=0, sticky="ew", pady=(0, 10))

        self.runtime_collapsed = tk.BooleanVar(value=True)
        self.runtime_toggle_btn = ttk.Button(
            runtime_container,
            text="▶ Runtime Options",
            command=self._toggle_runtime_options,
            width=20,
        )
        self.runtime_toggle_btn.pack(fill=tk.X)

        self.runtime_content_frame = ttk.Frame(
            runtime_container, relief=tk.GROOVE, borderwidth=2, padding=(10, 5)
        )
        self.runtime_content_frame.columnconfigure(1, weight=1)
        self.create_runtime_settings(self.runtime_content_frame)

        # Animation Settings
        self.anim_frame = ttk.LabelFrame(
            parent, text="Animation Settings", style="Bold.TLabelframe"
        )
        self.anim_frame.grid(row=3, column=0, sticky="nsew", pady=(0, 10))
        self.anim_frame.rowconfigure(0, weight=1)
        self.anim_frame.columnconfigure(0, weight=1)
        self.create_animation_settings(self.anim_frame)

        # Export Format radio buttons
        export_format_frame = ttk.Frame(parent)
        export_format_frame.grid(row=4, column=0, sticky="ew", pady=(0, 10))

        ttk.Label(
            export_format_frame, text="Export Format:", font=("Arial", 9, "bold")
        ).pack(side=tk.LEFT, padx=(0, 10))

        ttk.Radiobutton(
            export_format_frame,
            text="WAN",
            variable=self.export_format,
            value="WAN",
        ).pack(side=tk.LEFT, padx=(0, 10))

        ttk.Radiobutton(
            export_format_frame,
            text="EXTRACTED",
            variable=self.export_format,
            value="EXTRACTED",
        ).pack(side=tk.LEFT)

        # Process button
        self.generate_sprite_btn = ttk.Button(
            parent,
            text="Generate Sprite",
            command=self.generate_sprite,
            style="Large.TButton",
            state="disabled",
        )
        self.generate_sprite_btn.grid(row=5, column=0, sticky="ew", pady=(0, 10))

    def create_frames_generator_tab(self, parent):
        # Input Source
        selection_frame = ttk.LabelFrame(
            parent, text="Input Source", style="Bold.TLabelframe", padding=10
        )
        selection_frame.pack(fill=tk.X, pady=10, padx=10)

        input_frame = ttk.Frame(selection_frame)
        input_frame.pack(fill=tk.X)

        ttk.Entry(
            input_frame, textvariable=self.fg_input_display, width=30, state="readonly"
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))

        self.fg_folder_btn = ttk.Button(
            input_frame,
            text="Folder",
            command=lambda: self.browse_extracted_folder(
                self.fg_input_display,
                lambda path: self.prepare_validation_data(
                    1, path, self.validate_frames_generator_thread
                ),
            ),
            width=8,
        )
        self.fg_folder_btn.pack(side=tk.LEFT, padx=(0, 5))

        self.fg_wan_btn = ttk.Button(
            input_frame,
            text="WAN",
            command=lambda: self.browse_wan_file(
                self.fg_input_display,
                lambda path: self.prepare_validation_data(
                    1, path, self.validate_frames_generator_thread
                ),
            ),
            width=8,
        )
        self.fg_wan_btn.pack(side=tk.LEFT)

        # Optional Base Sprite for shared palette
        base_sprite_frame = ttk.LabelFrame(
            parent, text="Base Sprite (Optional)", style="Bold.TLabelframe", padding=10
        )
        base_sprite_frame.pack(fill=tk.X, pady=10, padx=10)

        base_input_frame = ttk.Frame(base_sprite_frame)
        base_input_frame.pack(fill=tk.X)

        ttk.Entry(
            base_input_frame,
            textvariable=self.fg_base_sprite_file,
            width=30,
            state="readonly",
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))

        self.fg_base_folder_btn = ttk.Button(
            base_input_frame,
            text="Folder",
            command=lambda: self.browse_extracted_folder(
                self.fg_base_sprite_file,
                lambda path: self.prepare_validation_data(
                    1,
                    path,
                    lambda p: self.validate_frames_generator_thread(p, "base"),
                    reset_data=False,
                ),
            ),
            width=8,
        )
        self.fg_base_folder_btn.pack(side=tk.LEFT, padx=(0, 5))

        self.fg_base_wan_btn = ttk.Button(
            base_input_frame,
            text="WAN",
            command=lambda: self.browse_wan_file(
                self.fg_base_sprite_file,
                lambda path: self.prepare_validation_data(
                    1,
                    path,
                    lambda p: self.validate_frames_generator_thread(p, "base"),
                    reset_data=False,
                ),
            ),
            width=8,
        )
        self.fg_base_wan_btn.pack(side=tk.LEFT)

        # Avoid Overlap Settings
        overlap_frame = ttk.LabelFrame(
            parent, text="Avoid Overlap", style="Bold.TLabelframe", padding=10
        )
        overlap_frame.pack(fill=tk.X, pady=10, padx=10)

        self.avoid_overlap = tk.StringVar(value="pixel")

        ttk.Radiobutton(
            overlap_frame,
            text="Pixel + Palette",
            variable=self.avoid_overlap,
            value="pixel",
        ).pack(anchor=tk.W, pady=2)

        ttk.Radiobutton(
            overlap_frame,
            text="Chunk + Palette",
            variable=self.avoid_overlap,
            value="chunk",
        ).pack(anchor=tk.W, pady=2)

        ttk.Radiobutton(
            overlap_frame, text="Palette", variable=self.avoid_overlap, value="palette"
        ).pack(anchor=tk.W, pady=2)

        ttk.Radiobutton(
            overlap_frame,
            text="None",
            variable=self.avoid_overlap,
            value="none",
        ).pack(anchor=tk.W, pady=2)

        self.generate_frames_btn = ttk.Button(
            parent,
            text="Generate Frames",
            command=self.generate_frames,
            style="Large.TButton",
            state="disabled",
        )
        self.generate_frames_btn.pack(fill=tk.X, pady=(10, 0), padx=10)

    def create_wan_io_tab(self, parent):
        # Generate Wan frame
        generate_frame = ttk.LabelFrame(
            parent, text="Generate Wan", style="Bold.TLabelframe", padding=20
        )
        generate_frame.pack(fill=tk.X, pady=10, padx=10)

        ttk.Label(
            generate_frame,
            text="Extracted WAN Folder:",
            font=("Arial", 12, "bold"),
        ).pack(anchor=tk.W, pady=(0, 5))

        folder_frame = ttk.Frame(generate_frame)
        folder_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Entry(
            folder_frame, textvariable=self.wan_io_folder, width=35, state="readonly"
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))

        self.wan_io_browse_folder_btn = ttk.Button(
            folder_frame,
            text="Browse",
            command=lambda: self.browse_extracted_folder(
                self.wan_io_folder,
                lambda path: self.prepare_validation_data(
                    2, path, self.validate_wan_io_thread
                ),
            ),
            width=10,
        )
        self.wan_io_browse_folder_btn.pack(side=tk.LEFT)

        # Generate Wan button
        self.wan_io_generate_btn = ttk.Button(
            generate_frame,
            text="Generate Wan",
            command=self.process_wan_io,
            style="Large.TButton",
            state="disabled",
        )
        self.wan_io_generate_btn.pack(fill=tk.X, pady=(10, 0))

        # Extract Wan frame
        extract_frame = ttk.LabelFrame(
            parent, text="Extract Wan", style="Bold.TLabelframe", padding=20
        )
        extract_frame.pack(fill=tk.X, pady=10, padx=10)

        ttk.Label(extract_frame, text="WAN File:", font=("Arial", 12, "bold")).pack(
            anchor=tk.W, pady=(0, 5)
        )

        wan_frame = ttk.Frame(extract_frame)
        wan_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Entry(
            wan_frame, textvariable=self.wan_io_wan_file, width=35, state="readonly"
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))

        self.wan_io_browse_wan_btn = ttk.Button(
            wan_frame,
            text="Browse",
            command=lambda: self.browse_wan_file(
                self.wan_io_wan_file,
                lambda path: self.prepare_validation_data(
                    2, path, self.validate_wan_io_thread
                ),
            ),
            width=10,
        )
        self.wan_io_browse_wan_btn.pack(side=tk.LEFT)

        # Extract Wan button
        self.wan_io_extract_btn = ttk.Button(
            extract_frame,
            text="Extract Wan",
            command=self.process_wan_io,
            style="Large.TButton",
            state="disabled",
        )
        self.wan_io_extract_btn.pack(fill=tk.X, pady=(10, 0))

    def create_basic_settings(self, parent):
        row = 0

        # Input Folder
        ttk.Label(parent, text="Frames Folder:", font=("Arial", 9, "bold")).grid(
            row=row, column=0, sticky=tk.W, pady=5
        )
        folder_frame = ttk.Frame(parent)
        folder_frame.grid(row=row, column=1, sticky=tk.EW)

        ttk.Entry(
            folder_frame, textvariable=self.input_folder, width=25, state="readonly"
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.browse_btn = ttk.Button(
            folder_frame, text="Browse", command=self.browse_folder, width=8
        )
        self.browse_btn.pack(side=tk.LEFT, padx=(5, 0))

        row += 1

        # Displace Sprite X and Y in one row with quick select dropdown
        ttk.Label(parent, text="Displace Sprite:", font=("Arial", 9, "bold")).grid(
            row=row, column=0, sticky=tk.W, pady=5
        )

        displace_frame = ttk.Frame(parent)
        displace_frame.grid(row=row, column=1, sticky=tk.EW, pady=5, padx=5)
        displace_frame.columnconfigure(1, weight=1)
        displace_frame.columnconfigure(3, weight=1)

        def validate_and_switch_to_custom(new_value):
            if not validate_integer_input(new_value):
                return False
            self.quick_select_var.set("Custom")
            return True

        validate_and_switch_cmd = (
            self.root.register(validate_and_switch_to_custom),
            "%P",
        )

        ttk.Label(displace_frame, text="X:").grid(row=0, column=0, sticky="w")
        x_spinbox = ttk.Spinbox(
            displace_frame,
            from_=-999999,
            to=999999,
            textvariable=self.displace_x,
            validate="key",
            validatecommand=validate_and_switch_cmd,
        )
        x_spinbox.grid(row=0, column=1, sticky="ew", padx=(2, 10))

        ttk.Label(displace_frame, text="Y:").grid(row=0, column=2, sticky="w")
        y_spinbox = ttk.Spinbox(
            displace_frame,
            from_=-999999,
            to=999999,
            textvariable=self.displace_y,
            validate="key",
            validatecommand=validate_and_switch_cmd,
        )
        y_spinbox.grid(row=0, column=3, sticky="ew", padx=(2, 10))

        def set_displacement(position):
            if not position or position == "Custom":
                return
            w = 0 if self.sg_image_width is None else self.sg_image_width // 2
            h = 0 if self.sg_image_height is None else self.sg_image_height // 2

            if position == "TopL":
                x, y = w, h
            elif position == "TopR":
                x, y = -w, h
            elif position == "Center":
                x, y = 0, 0
            elif position == "BottomL":
                x, y = w, -h
            elif position == "BottomR":
                x, y = -w, -h
            else:
                return

            self.displace_x.set(x)
            self.displace_y.set(y)

        # Quick select dropdown
        quick_select_combo = ttk.Combobox(
            displace_frame,
            textvariable=self.quick_select_var,
            values=["Center", "TopL", "TopR", "BottomL", "BottomR"],
            state="readonly",
            width=10,
        )
        quick_select_combo.grid(row=0, column=4, sticky="ew")

        def on_combobox_selected(event):
            set_displacement(self.quick_select_var.get())
            quick_select_combo.selection_clear()

        quick_select_combo.bind("<<ComboboxSelected>>", on_combobox_selected)

        row += 1

        # Sprite Category
        ttk.Label(parent, text="Sprite Category:", font=("Arial", 9, "bold")).grid(
            row=row, column=0, sticky=tk.W, pady=5
        )

        category_frame = ttk.Frame(parent)
        category_frame.grid(row=row, column=1, sticky=tk.EW, pady=5, padx=5)

        def on_category_changed(event=None):
            category = self.sprite_category.get()
            self._update_category_props_visibility(category)
            category_combo.selection_clear()

        category_combo = ttk.Combobox(
            category_frame,
            textvariable=self.sprite_category,
            values=list(CATEGORY_CHECKBOX_MAP.keys()),
            state="readonly",
        )
        category_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        category_combo.bind("<<ComboboxSelected>>", on_category_changed)

        row += 1

        # Category checkboxes - unified frame with individually controlled checkboxes
        self.category_props_frame = ttk.Frame(parent)
        self.category_props_frame.grid(
            row=row, column=0, columnspan=2, sticky="ew", pady=5, padx=5
        )

        ttk.Label(
            self.category_props_frame, text="Flags:", font=("Arial", 9, "bold")
        ).pack(side=tk.LEFT, padx=(0, 10))

        # Store checkbox widgets for per-category visibility control
        self.category_checkboxes = {}

        self.category_checkboxes["tiles_mode"] = ttk.Checkbutton(
            self.category_props_frame, text="Tiles Mode", variable=self.use_tiles_mode
        )
        self.category_checkboxes["tiles_mode"].pack(side=tk.LEFT)

        self.category_checkboxes["used_base_palette"] = ttk.Checkbutton(
            self.category_props_frame,
            text="Base Palette",
            variable=self.used_base_palette,
        )
        self.category_checkboxes["used_base_palette"].pack(side=tk.LEFT, padx=(10, 0))

        row += 1

    def create_runtime_settings(self, parent):
        row = 0

        # Min Row Column Density
        ttk.Label(parent, text="Min Density:", font=("Arial", 9, "bold")).grid(
            row=row, column=0, sticky=tk.W, pady=5
        )
        density_frame = ttk.Frame(parent)
        density_frame.grid(row=row, column=1, sticky=tk.EW, pady=5, padx=5)
        density_frame.columnconfigure(0, weight=1)

        def update_density_label(v):
            self.density_label.config(text=f"{self.min_density.get()}%")

        ttk.Scale(
            density_frame,
            from_=0,
            to=100,
            variable=self.min_density,
            orient=tk.HORIZONTAL,
            length=230,
            command=update_density_label,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 5))

        self.density_label = tk.Label(density_frame, text=f"50%", width=5)
        self.density_label.grid(row=0, column=1)

        row += 1

        # Scan Options Section
        ttk.Label(parent, text="Scan Option:", font=("Arial", 9, "bold")).grid(
            row=row, column=0, sticky=tk.W, pady=5
        )

        scan_frame = ttk.Frame(parent)
        scan_frame.grid(row=row, column=1, sticky=tk.W, pady=5, padx=5)

        self.intrascan_var = tk.BooleanVar(value=True)
        self.interscan_var = tk.BooleanVar(value=True)

        ttk.Checkbutton(
            scan_frame, text="Intra Frame", variable=self.intrascan_var
        ).pack(side=tk.LEFT, padx=(0, 15))

        ttk.Checkbutton(
            scan_frame, text="Inter Frame", variable=self.interscan_var
        ).pack(side=tk.LEFT)

        row += 1

        # Chunk Sizes Section (flattened)
        ttk.Label(parent, text="Chunk Sizes:", font=("Arial", 9, "bold")).grid(
            row=row, column=0, columnspan=2, sticky=tk.W, pady=(5, 0)
        )

        row += 1

        chunk_sizes_frame = ttk.Frame(parent)
        chunk_sizes_frame.grid(row=row, column=0, columnspan=2, sticky=tk.EW, pady=5)

        self.scan_chunk_sizes = {}
        labels = [f"{w}x{h}" for w, h in CHUNK_SIZES]

        for col in range(6):
            chunk_sizes_frame.columnconfigure(col, weight=1)

        for i, label in enumerate(labels):
            cb_row = i // 6
            cb_col = i % 6

            is_enabled = i < len(labels) - 3
            var = tk.BooleanVar(value=is_enabled)
            self.scan_chunk_sizes[label] = var

            cb = ttk.Checkbutton(chunk_sizes_frame, text=label, variable=var)
            cb.grid(row=cb_row, column=cb_col, sticky=tk.W, padx=2, pady=2)

    def _toggle_runtime_options(self):
        if self.runtime_collapsed.get():
            self.runtime_content_frame.pack(fill=tk.BOTH, expand=True, pady=(5, 0))
            self.runtime_toggle_btn.config(text="▼ Runtime Options")
            self.anim_frame.grid_remove()  # Hide animation settings
            self.runtime_collapsed.set(False)
        else:
            self.runtime_content_frame.pack_forget()
            self.runtime_toggle_btn.config(text="▶ Runtime Options")
            self.anim_frame.grid()  # Show animation settings
            self.runtime_collapsed.set(True)

    def _update_category_props_visibility(self, category=None):
        if category is None:
            category = self.sprite_category.get()

        # Get which checkboxes to show for this category
        visible_checkboxes = CATEGORY_CHECKBOX_MAP.get(category, [])

        # Show/hide each checkbox based on config
        first_visible = True
        for checkbox_key, checkbox_widget in self.category_checkboxes.items():
            if checkbox_key in visible_checkboxes:
                padx = (0, 0) if first_visible else (10, 0)
                checkbox_widget.pack(side=tk.LEFT, padx=padx)
                first_visible = False
            else:
                checkbox_widget.pack_forget()

        # Show/hide the entire props frame
        if visible_checkboxes:
            self.category_props_frame.grid()
        else:
            self.category_props_frame.grid_remove()

    def create_animation_settings(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.columnconfigure(1, weight=0)

        # Animation group list
        list_frame = ttk.Frame(parent)
        list_frame.grid(row=0, column=0, sticky="nsew", pady=(10, 18), padx=(10, 5))
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)

        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.grid(row=0, column=1, sticky="ns")

        self.anim_group_listbox = tk.Listbox(
            list_frame, yscrollcommand=scrollbar.set, height=8
        )
        self.anim_group_listbox.grid(row=0, column=0, sticky="nsew")
        scrollbar.config(command=self.anim_group_listbox.yview)

        # Animation Buttons - vertically stacked
        btn_frame = ttk.Frame(parent)
        btn_frame.grid(row=0, column=1, sticky="n", pady=(10, 18), padx=(5, 10))
        btn_frame.columnconfigure(0, weight=1)

        ttk.Button(
            btn_frame,
            text="Add Animation",
            command=self.add_animation_sequence,
        ).grid(row=0, column=0, sticky="ew", pady=2)
        ttk.Button(
            btn_frame,
            text="Edit Animation",
            command=self.edit_animation_sequence,
        ).grid(row=1, column=0, sticky="ew", pady=2)
        ttk.Button(
            btn_frame, text="Delete", command=self.delete_frame_or_sequence
        ).grid(row=2, column=0, sticky="ew", pady=2)
        ttk.Button(
            btn_frame,
            text="View Animations",
            command=self.view_animation_sequences,
        ).grid(row=3, column=0, sticky="ew", pady=2)

        self.animation_group = []
        self.update_animation_group_listbox()

    def create_console(self, parent):
        self.console_text = scrolledtext.ScrolledText(
            parent,
            wrap=tk.WORD,
            bg="#1e1e1e",
            fg="#00ff00",
            font=("Consolas", 9),
            state="disabled",
        )
        self.console_text.pack(fill=tk.BOTH, expand=True)

        self.clear_console_btn = ttk.Button(
            parent, text="Clear", command=self.clear_console, width=8
        )
        self.clear_console_btn.place(relx=1.0, rely=1.0, anchor=tk.SE, x=-30, y=-10)

    def check_for_update(self):
        try:
            with urllib.request.urlopen(RELEASE_API_ENDPOINT, timeout=5) as response:
                if response.status != 200:
                    raise Exception(f"HTTP Error {response.status}: {response.reason}")

                data = response.read()
                latest_version = (
                    json.loads(data).get("name", "").replace("Version ", "")
                )

                if latest_version and CURRENT_VERSION != latest_version:
                    messagebox.showinfo(
                        "Update Available",
                        f"Version {latest_version} is now available. Please update.",
                    )
                elif DEBUG:
                    print("[OK] Up to date.")
        except Exception as e:
            if DEBUG:
                print(f"[WARNING] Could not check for updates. \n{e}")

    def browse_folder(self):
        folder = filedialog.askdirectory(
            initialdir=self.input_folder.get() if self.input_folder.get() else "."
        )

        if not folder:
            return

        prev_animation_group = None

        if folder != self.input_folder.get():
            self.displace_x.set(0)
            self.displace_y.set(0)
            self.quick_select_var.set("Center")
            self.input_folder.set(folder)
        else:
            prev_animation_group = self.animation_group

        def set_animation_for_folder():
            if prev_animation_group:
                result = self.validate_config_values(
                    animation_group=prev_animation_group,
                )

                valid_values = result["valid_values"]

                if "animation_group" in valid_values:
                    self.animation_group = valid_values["animation_group"]
                else:
                    self.animation_group = []
            else:
                self.animation_group = []

            if not self.animation_group and self.sg_available_frames:
                min_frame = self.sg_available_frames[0]
                self.animation_group = [
                    [
                        {
                            "frame": min_frame,
                            "duration": DEFAULT_ANIMATION_DURATION,
                        }
                    ]
                ]

            self.update_animation_group_listbox()

        self.prepare_sprite_generator_data(on_complete=set_animation_for_folder)

    def browse_extracted_folder(self, folder_var, validation_func):
        folder = filedialog.askdirectory(
            initialdir=folder_var.get() if folder_var.get() else "."
        )

        if not folder:
            return

        folder_var.set(folder)

        if folder_var is self.wan_io_folder:
            self.wan_io_wan_file.set("")

        validation_func(Path(folder))

    def browse_wan_file(self, wan_var, validation_func):
        wan_file = filedialog.askopenfilename(
            title="Select WAN File",
            initialdir=(str(Path(wan_var.get()).parent) if wan_var.get() else "."),
            filetypes=[("WAN files", "*.wan"), ("All files", "*.*")],
        )

        if not wan_file:
            return

        wan_var.set(wan_file)

        if wan_var is self.wan_io_wan_file:
            self.wan_io_folder.set("")

        validation_func(Path(wan_file))

    def add_animation_sequence(self):
        if not self.sg_available_frames:
            messagebox.showwarning(
                "No Folder Selected", "Please select a folder with valid images first"
            )
            return

        animation_number = len(self.animation_group) + 1
        dialog = AnimationEditorDialog(
            self.root,
            f"Adding Animation {animation_number}",
            available_frames=self.sg_available_frames,
            frame_images=self.frame_number_to_image,
        )

        if dialog.result:
            self.animation_group.append(dialog.result)
            self.update_animation_group_listbox()

    def edit_animation_sequence(self):
        selection = self.anim_group_listbox.curselection()
        if not selection:
            messagebox.showwarning(
                "No Selection", "Please select a animation sequence to edit"
            )
            return

        # Find which group the selected item belongs to
        selected_line = selection[0]
        group_idx = self.get_group_index_from_line(selected_line)

        dialog = AnimationEditorDialog(
            self.root,
            f"Editing Animation {group_idx + 1}",
            initial_data=self.animation_group[group_idx],
            available_frames=self.sg_available_frames,
            frame_images=self.frame_number_to_image,
        )
        if dialog.result:
            self.animation_group[group_idx] = dialog.result
            self.update_animation_group_listbox()

    def delete_frame_or_sequence(self):
        # Get the selected item
        selection = self.anim_group_listbox.curselection()
        if not selection:
            messagebox.showwarning(
                "No Selection", "Please select an animation or frame to delete"
            )
            return

        selected_line = selection[0]
        selected_text = self.anim_group_listbox.get(selected_line)

        # Check if a frame is selected (starts with tree characters)
        is_frame = selected_text.startswith("├──") or selected_text.startswith("└──")

        if is_frame:
            # === DELETING A FRAME ===
            group_idx, frame_idx, frame_no = self.get_frame_indices_from_line(
                selected_line
            )

            if group_idx is None or frame_idx is None:
                return

            # Check if this would delete the last frame of the last sequence
            is_last_sequence = len(self.animation_group) == 1
            is_last_frame_in_sequence = len(self.animation_group[group_idx]) == 1

            if is_last_sequence and is_last_frame_in_sequence:
                messagebox.showwarning(
                    "Cannot Delete", "At least one animation with one frame must exist."
                )
                return

            # Confirm and delete
            if messagebox.askyesno(
                "Confirm Delete",
                f"Delete frame {frame_no} from animation {group_idx + 1}?",
            ):
                del self.animation_group[group_idx][frame_idx]

                # If group becomes empty after deleting frame, remove the group too
                if not self.animation_group[group_idx]:
                    del self.animation_group[group_idx]

                self.update_animation_group_listbox()

        else:
            # === DELETING AN ENTIRE SEQUENCE ===
            group_idx = self.get_group_index_from_line(selected_line)

            if group_idx is None:
                return

            # Check if this is the last sequence
            is_last_sequence = len(self.animation_group) == 1

            if is_last_sequence:
                messagebox.showwarning(
                    "Cannot Delete", "At least one animation sequence must exist."
                )
                return

            # Confirm and delete
            if messagebox.askyesno(
                "Confirm Delete", f"Delete animation sequence {group_idx + 1}?"
            ):
                del self.animation_group[group_idx]
                self.update_animation_group_listbox()

    def view_animation_sequences(self):
        if not self.animation_group:
            messagebox.showwarning("No Animations", "No animation sequences to view.")
            return

        # Create the viewer window
        AnimationViewer(
            self.root,
            "Animation Viewer",
            self.frame_number_to_image,
            self.animation_group,
        )

    def get_group_index_from_line(self, line_idx):
        current_line = 0

        for group_idx, group in enumerate(self.animation_group):
            # Group header line
            if current_line == line_idx:
                return group_idx
            current_line += 1

            # Frame lines
            frame_count = len(group)
            if current_line <= line_idx < current_line + frame_count:
                return group_idx
            current_line += frame_count

        return None

    def get_frame_indices_from_line(self, line_idx):
        current_line = 0

        for group_idx, group in enumerate(self.animation_group):
            # Group header line
            current_line += 1

            # Frame lines
            for frame_idx, frame_data in enumerate(group):
                if current_line == line_idx:
                    return (group_idx, frame_idx, frame_data["frame"])
                current_line += 1

        return (None, None, None)

    def update_animation_group_listbox(self):
        self.anim_group_listbox.delete(0, tk.END)
        for i, group in enumerate(self.animation_group):
            # Add group header
            self.anim_group_listbox.insert(tk.END, f"Animation {i+1}")

            # Add frames with tree structure
            for idx, frame_data in enumerate(group):
                is_last = idx == len(group) - 1
                prefix = "└── " if is_last else "├── "
                frame_num = frame_data["frame"]
                duration = frame_data["duration"]
                self.anim_group_listbox.insert(
                    tk.END, f"{prefix}Frame {frame_num}: {duration}"
                )

    def clear_console(self, event=None):
        self.console_text.config(state="normal")
        self.console_text.delete(1.0, tk.END)
        self.console_text.config(state="disabled")

    def save_config(self):

        # Convert BooleanVar checkboxes to a simple dict
        chunk_sizes_config = {
            label: var.get() for label, var in self.scan_chunk_sizes.items()
        }

        config = {
            "frames_folder": self.input_folder.get(),
            "min_density": self.min_density.get(),
            "displace_x": self.displace_x.get(),
            "displace_y": self.displace_y.get(),
            "intrascan": self.intrascan_var.get(),
            "interscan": self.interscan_var.get(),
            "scan_chunk_sizes": chunk_sizes_config,
            "animation_group": self.animation_group,
            "export_format": self.export_format.get(),
            "sprite_category": self.sprite_category.get(),
            "custom_properties": {
                "use_tiles_mode": self.use_tiles_mode.get(),
                "used_base_palette": self.used_base_palette.get(),
            },
        }

        file_path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )

        if file_path:
            write_json_file(Path(file_path), config)
            messagebox.showinfo("Success", "Configuration saved successfully")

    def load_config(self):
        file_path = filedialog.askopenfilename(
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if not file_path:
            return

        config = read_json_file(Path(file_path))
        if config is None:
            messagebox.showerror(
                "Error", "Failed to load config file or file is invalid."
            )
            return

        try:
            loaded_folder_str = config.get("frames_folder")
            loaded_folder = Path(loaded_folder_str)
            if not loaded_folder.exists():
                messagebox.showerror(
                    "Folder Not Found", f"Folder does not exist:\n{loaded_folder}"
                )
                return

            self.input_folder.set(loaded_folder_str)

            def apply_config_values():
                # ---- Validate config values ----
                result = self.validate_config_values(
                    animation_group=config.get("animation_group"),
                    min_density=config.get("min_density"),
                    displace_x=config.get("displace_x"),
                    displace_y=config.get("displace_y"),
                    intrascan=config.get("intrascan"),
                    interscan=config.get("interscan"),
                    scan_chunk_sizes=config.get("scan_chunk_sizes"),
                    export_format=config.get("export_format"),
                    sprite_category=config.get("sprite_category"),
                    custom_properties=config.get("custom_properties"),
                )

                valid = result["valid_values"]
                invalid_values = result["invalid_values"]

                # ---- Apply valid values ----
                if "min_density" in valid:
                    self.min_density.set(valid["min_density"])
                    self.density_label.config(text=f"{self.min_density.get()}%")
                else:
                    self.min_density.set(50)
                    self.density_label.config(text="50%")

                if "displace_x" in valid:
                    self.displace_x.set(valid["displace_x"])
                else:
                    self.displace_x.set(0)

                if "displace_y" in valid:
                    self.displace_y.set(valid["displace_y"])
                else:
                    self.displace_y.set(0)

                # Reset to Center if both are 0
                if self.displace_x.get() == 0 and self.displace_y.get() == 0:
                    self.quick_select_var.set("Center")

                if "intrascan" in valid:
                    self.intrascan_var.set(valid["intrascan"])
                else:
                    self.intrascan_var.set(True)

                if "interscan" in valid:
                    self.interscan_var.set(valid["interscan"])
                else:
                    self.interscan_var.set(True)

                if "scan_chunk_sizes" in valid:
                    for label in self.scan_chunk_sizes.keys():
                        if label in valid["scan_chunk_sizes"]:
                            self.scan_chunk_sizes[label].set(
                                valid["scan_chunk_sizes"][label]
                            )
                        else:
                            labels_list = [f"{w}x{h}" for w, h in CHUNK_SIZES]
                            label_index = (
                                labels_list.index(label) if label in labels_list else -1
                            )
                            is_enabled = label_index < len(labels_list) - 3
                            self.scan_chunk_sizes[label].set(is_enabled)
                else:
                    labels_list = [f"{w}x{h}" for w, h in CHUNK_SIZES]
                    for label in self.scan_chunk_sizes.keys():
                        label_index = (
                            labels_list.index(label) if label in labels_list else -1
                        )
                        is_enabled = label_index < len(labels_list) - 3
                        self.scan_chunk_sizes[label].set(is_enabled)

                if "animation_group" in valid:
                    self.animation_group = valid["animation_group"]
                elif self.sg_available_frames:
                    min_frame = self.sg_available_frames[0]
                    self.animation_group = [
                        [
                            {
                                "frame": min_frame,
                                "duration": DEFAULT_ANIMATION_DURATION,
                            }
                        ]
                    ]

                if "export_format" in valid:
                    self.export_format.set(valid["export_format"])
                else:
                    self.export_format.set("WAN")

                # Apply sprite_category (stored as display name now)
                if "sprite_category" in valid:
                    self.sprite_category.set(valid["sprite_category"])
                else:
                    self.sprite_category.set("4bpp Standalone")

                # Apply custom_properties (each field individually so one wrong value doesn't reset others)
                props = valid.get("custom_properties", {})
                self.use_tiles_mode.set(props.get("use_tiles_mode", False))
                self.used_base_palette.set(props.get("used_base_palette", False))

                # Update UI visibility based on sprite_category
                self._update_category_props_visibility()

                self.update_animation_group_listbox()

                # ---- Show warning if there are invalid values ----
                if invalid_values:
                    error_lines = []
                    for k, v in invalid_values.items():
                        if "\n" in v:
                            error_lines.append(f"Errors in {k}:")
                            for line in v.split("\n"):
                                error_lines.append(f"  • {line}")
                        else:
                            error_lines.append(f"Error in {k}:")
                            error_lines.append(f"  • {v}")

                    invalid_str = "\n".join(error_lines)
                    messagebox.showwarning(
                        "Invalid Config Values",
                        f"The following values were ignored:\n\n{invalid_str}",
                    )

            self.prepare_sprite_generator_data(on_complete=apply_config_values)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load config: {str(e)}")

    def validate_config_values(
        self,
        animation_group=None,
        min_density=None,
        displace_x=None,
        displace_y=None,
        intrascan=None,
        interscan=None,
        scan_chunk_sizes=None,
        export_format=None,
        sprite_category=None,
        custom_properties=None,
    ):
        invalid_values = {}
        valid_values = {}

        # ---- Validate sprite_category (accepts display names now) ----
        if sprite_category is not None:
            if not isinstance(sprite_category, str):
                invalid_values["sprite_category"] = (
                    f"Must be a string. Received: {type(sprite_category).__name__}."
                )
            elif sprite_category not in CATEGORY_CHECKBOX_MAP:
                invalid_values["sprite_category"] = (
                    f"Must be one of {list(CATEGORY_CHECKBOX_MAP.keys())}. Received: {sprite_category}."
                )
            else:
                valid_values["sprite_category"] = sprite_category

        # ---- Validate custom_properties ----
        if custom_properties is not None:
            if not isinstance(custom_properties, dict):
                invalid_values["custom_properties"] = (
                    f"Must be a dictionary. Received: {type(custom_properties).__name__}."
                )
            else:
                valid_props = {}
                invalid_prop_errors = []

                # Validate boolean properties
                for key in ["use_tiles_mode", "used_base_palette"]:
                    if key in custom_properties:
                        val = custom_properties[key]
                        if not isinstance(val, bool):
                            invalid_prop_errors.append(
                                f"'{key}': Must be true or false. Received: {type(val).__name__}."
                            )
                        else:
                            valid_props[key] = val

                if invalid_prop_errors:
                    invalid_values["custom_properties"] = "\n".join(invalid_prop_errors)

                if valid_props:
                    valid_values["custom_properties"] = valid_props

        # ---- Validate min_density ----
        if min_density is not None:
            if not isinstance(min_density, int):
                invalid_values["min_density"] = (
                    f"Must be a whole number. Received: {type(min_density).__name__}."
                )
            elif not (0 <= min_density <= 100):
                invalid_values["min_density"] = (
                    f"Must be between 0 and 100. Received: {min_density}."
                )
            else:
                valid_values["min_density"] = min_density

        # ---- Validate displace_x / displace_y ----
        for key, val in {"displace_x": displace_x, "displace_y": displace_y}.items():
            if val is None:
                continue
            if not isinstance(val, int):
                invalid_values[key] = (
                    f"Must be a whole number. Received: {type(val).__name__}."
                )
            elif not (-999999 <= val <= 999999):
                invalid_values[key] = (
                    f"Must be between -999999 and 999999. Received: {val}."
                )
            else:
                valid_values[key] = val

        # ---- Validate intrascan / interscan ----
        for key, val in {"intrascan": intrascan, "interscan": interscan}.items():
            if val is None:
                continue
            if not isinstance(val, bool):
                invalid_values[key] = (
                    f"Must be true or false. Received: {type(val).__name__}."
                )
            else:
                valid_values[key] = val

        # ---- Validate scan_chunk_sizes ----
        if scan_chunk_sizes is not None:
            if not isinstance(scan_chunk_sizes, dict):
                invalid_values["scan_chunk_sizes"] = (
                    f"Must be a dictionary of chunk sizes (e.g., {{'32x32': true, '16x16': false}}). Received: {type(scan_chunk_sizes).__name__}."
                )
            else:
                valid_chunk_sizes = {}
                invalid_chunk_errors = []
                valid_labels = {f"{w}x{h}" for w, h in CHUNK_SIZES}

                for label, value in scan_chunk_sizes.items():
                    if label not in valid_labels:
                        invalid_chunk_errors.append(f"'{label}': Invalid chunk size.")
                    elif not isinstance(value, bool):
                        invalid_chunk_errors.append(
                            f"'{label}': Must be true or false. Received: {type(value).__name__}."
                        )
                    else:
                        valid_chunk_sizes[label] = value

                if invalid_chunk_errors:
                    invalid_values["scan_chunk_sizes"] = "\n".join(invalid_chunk_errors)

                if valid_chunk_sizes:
                    valid_values["scan_chunk_sizes"] = valid_chunk_sizes

        # ---- Validate export_format ----
        if export_format is not None:
            if not isinstance(export_format, str):
                invalid_values["export_format"] = (
                    f"Must be a string. Received: {type(export_format).__name__}."
                )
            elif export_format not in ("WAN", "EXTRACTED"):
                invalid_values["export_format"] = (
                    f"Must be 'WAN' or 'EXTRACTED'. Received: {export_format}."
                )
            else:
                valid_values["export_format"] = export_format

        # ---- Validate animation_group ----
        if animation_group is not None:
            if not isinstance(animation_group, list):
                invalid_values["animation_group"] = (
                    f"Must be a list of animations. Received: {type(animation_group).__name__}."
                )
            elif not self.sg_available_frames:
                invalid_values["animation_group"] = (
                    "Cannot validate animations: No available frames found in selected folder."
                )
            else:
                cleaned_animation_group = []
                invalid_anim_errors = []

                for group_idx, group in enumerate(animation_group):
                    if not isinstance(group, list):
                        invalid_anim_errors.append(
                            f"Animation {group_idx + 1}: Must be a list of frame entries. Received: {type(group).__name__}."
                        )
                        continue

                    cleaned_group = []
                    for frame_idx, frame_data in enumerate(group):
                        if not isinstance(frame_data, dict):
                            invalid_anim_errors.append(
                                f"Animation {group_idx + 1}, Entry {frame_idx + 1}: Must be a dictionary with 'frame' and 'duration' fields. Received: {type(frame_data).__name__}."
                            )
                            continue

                        frame_num = frame_data.get("frame")
                        duration = frame_data.get("duration")

                        # Check frame number
                        if frame_num is None:
                            invalid_anim_errors.append(
                                f"Animation {group_idx + 1}, Entry {frame_idx + 1}: Missing 'frame' field."
                            )
                            continue
                        elif not isinstance(frame_num, int):
                            invalid_anim_errors.append(
                                f"Animation {group_idx + 1}, Entry {frame_idx + 1}: 'frame' must be a whole number. Received: {type(frame_num).__name__}."
                            )
                            continue
                        elif frame_num not in self.sg_available_frames:
                            invalid_anim_errors.append(
                                f"Animation {group_idx + 1}, Entry {frame_idx + 1}: Frame {frame_num} not found."
                            )
                            continue

                        # Check duration
                        if duration is None:
                            invalid_anim_errors.append(
                                f"Animation {group_idx + 1}, Entry {frame_idx + 1}: Missing 'duration' field."
                            )
                            continue
                        elif not isinstance(duration, int):
                            invalid_anim_errors.append(
                                f"Animation {group_idx + 1}, Entry {frame_idx + 1}: 'duration' must be a whole number. Received: {type(duration).__name__}."
                            )
                            continue
                        elif duration <= 0:
                            invalid_anim_errors.append(
                                f"Animation {group_idx + 1}, Entry {frame_idx + 1}: 'duration' must be greater than 0. Received: {duration}."
                            )
                            continue

                        cleaned_group.append({"frame": frame_num, "duration": duration})

                    if cleaned_group:
                        cleaned_animation_group.append(cleaned_group)

                if invalid_anim_errors:
                    invalid_values["animation_group"] = "\n".join(invalid_anim_errors)

                if cleaned_animation_group:
                    valid_values["animation_group"] = cleaned_animation_group

        return {
            "invalid_values": invalid_values,
            "valid_values": valid_values,
        }

    def disable_ui_for_processing(self, tab_index: int):
        # Disable all tabs except the current one
        for i in range(3):
            if i != tab_index:
                self.notebook.tab(i, state="disabled")

        # Disable clear button
        self.clear_console_btn.config(state="disabled")

        # Disable tab-specific buttons
        if tab_index == 0:  # Sprite Generator
            self.generate_sprite_btn.config(state="disabled")
            self.browse_btn.config(state="disabled")
            self.load_config_btn.config(state="disabled")
        elif tab_index == 1:  # Frames Generator
            self.generate_frames_btn.config(state="disabled")
            self.fg_folder_btn.config(state="disabled")
            self.fg_wan_btn.config(state="disabled")
            self.fg_base_folder_btn.config(state="disabled")
            self.fg_base_wan_btn.config(state="disabled")
        elif tab_index == 2:  # Wan IO
            self.wan_io_extract_btn.config(state="disabled")
            self.wan_io_generate_btn.config(state="disabled")
            self.wan_io_browse_folder_btn.config(state="disabled")
            self.wan_io_browse_wan_btn.config(state="disabled")

    def enable_ui_after_processing(
        self, tab_index: int, enable_action_buttons: bool = True
    ):
        # Enable all tabs
        for i in range(3):

            def enable_tab(idx=i):
                self.notebook.tab(idx, state="normal")

            self.root.after(0, enable_tab)

        # Enable clear button
        self.root.after(0, lambda: self.clear_console_btn.config(state="normal"))

        # Enable tab-specific buttons
        if tab_index == 0:  # Sprite Generator
            if enable_action_buttons:
                self.root.after(
                    0, lambda: self.generate_sprite_btn.config(state="normal")
                )
            self.root.after(0, lambda: self.browse_btn.config(state="normal"))
            self.root.after(0, lambda: self.load_config_btn.config(state="normal"))
        elif tab_index == 1:  # Frames Generator
            if enable_action_buttons:
                self.root.after(
                    0, lambda: self.generate_frames_btn.config(state="normal")
                )
            self.root.after(0, lambda: self.fg_folder_btn.config(state="normal"))
            self.root.after(0, lambda: self.fg_wan_btn.config(state="normal"))
            self.root.after(0, lambda: self.fg_base_folder_btn.config(state="normal"))
            self.root.after(0, lambda: self.fg_base_wan_btn.config(state="normal"))
        elif tab_index == 2:  # Wan IO
            # enable based on wan_io_is_folder
            if enable_action_buttons:
                if self.wan_io_is_folder:
                    self.root.after(
                        0, lambda: self.wan_io_generate_btn.config(state="normal")
                    )
                else:
                    self.root.after(
                        0, lambda: self.wan_io_extract_btn.config(state="normal")
                    )
            self.root.after(
                0, lambda: self.wan_io_browse_folder_btn.config(state="normal")
            )
            self.root.after(
                0, lambda: self.wan_io_browse_wan_btn.config(state="normal")
            )

    def prepare_sprite_generator_data(self, on_complete=None):
        self.disable_ui_for_processing(0)  # Tab 0 = Sprite Generator

        # Reset Frame Images for Viewer
        self.frame_number_to_image = {}

        # Reset validation data
        self.sg_images_dict = {}
        self.sg_shared_palette = None
        self.sg_max_colors_used = None
        self.sg_image_height = None
        self.sg_image_width = None
        self.sg_available_frames = []

        folder_str = self.input_folder.get()
        if folder_str:
            folder = Path(folder_str)
            if not folder.exists():
                self.enable_ui_after_processing(0)
                return
        else:
            self.enable_ui_after_processing(0)
            return

        self.clear_console()

        thread = threading.Thread(
            target=self.validate_sprite_generator_thread, args=(folder, on_complete)
        )
        thread.daemon = True
        thread.start()

    def validate_sprite_generator_thread(self, folder: Path, on_complete=None):
        images_dict = None
        common_image_size = None
        original_shared_palette = None
        max_colors_used = None
        available_frames = None

        def complete_validation():
            if (
                images_dict
                and common_image_size
                and original_shared_palette
                and available_frames
            ):
                self.sg_images_dict = images_dict
                self.sg_image_width = common_image_size[0]
                self.sg_image_height = common_image_size[1]
                self.sg_shared_palette = original_shared_palette
                self.sg_max_colors_used = max_colors_used
                self.sg_available_frames = available_frames

                local_frame_number_to_image = {}
                frames_found = {}

                for data in self.sg_images_dict.values():
                    frame_num, layer_num, _ = data["frame_layer_palette_tuple"]
                    frames_found.setdefault(frame_num, []).append(
                        (layer_num, data["image_data"])
                    )

                # Composite each frame for viewer
                frame_numbers = sorted(frames_found.keys())
                for frame_no in frame_numbers:
                    layers = sorted(frames_found[frame_no], key=lambda x: x[0])
                    base = None
                    for _, img in layers:
                        base = img if base is None else Image.alpha_composite(base, img)

                    local_frame_number_to_image[frame_no] = ImageTk.PhotoImage(base)

                self.frame_number_to_image = local_frame_number_to_image

                if DEBUG:
                    print(
                        f"[OK] Composite images created for frames: {self.sg_available_frames}\n"
                    )

                print(f"[OK] Available Frames: {self.sg_available_frames}")

                # Enable process button
                self.root.after(
                    0, lambda: self.generate_sprite_btn.config(state="normal")
                )
                print("\n[OK] Validation Successful. Ready to generate.")

                on_complete and on_complete()

        try:
            (
                images_dict,
                common_image_size,
                original_shared_palette,
                max_colors_used,
                available_frames,
            ) = validate_sg_input_folder(folder)
        except Exception as e:
            print(f"\n[ERROR] Validation error:\n{str(e)}")
        finally:
            self.root.after(0, complete_validation)
            self.enable_ui_after_processing(
                0, enable_action_buttons=False
            )  # Tab 0 = Sprite Generator (action button enabled conditionally)

    def generate_sprite(self):
        self.clear_console()
        self.disable_ui_for_processing(0)  # Tab 0 = Sprite Generator
        thread = threading.Thread(target=self.generate_sprite_thread)
        thread.daemon = True
        thread.start()

    def generate_sprite_thread(self):
        try:
            try:
                displace_x = self.displace_x.get()
                displace_y = self.displace_y.get()
            except tk.TclError:
                print(
                    f"\n[WARNING] Displace X and Y values cannot be empty — using 0 as default"
                )
                self.displace_x.set(0)
                self.displace_y.set(0)
                displace_x = 0
                displace_y = 0

            displace_sprite = [displace_x, displace_y]
            min_row_column_density = self.min_density.get() / 100
            animation_group = self.animation_group
            scan_chunk_sizes = [
                tuple(map(int, label.split("x")))
                for label, var in self.scan_chunk_sizes.items()
                if var.get()
            ]

            intra_scan = self.intrascan_var.get()
            inter_scan = self.interscan_var.get()
            input_folder = Path(self.input_folder.get())
            export_format = self.export_format.get()
            export_as_wan = True if export_format == "WAN" else False

            # Sprite category and custom properties
            sprite_category = self.sprite_category.get()
            custom_properties = {
                "use_tiles_mode": self.use_tiles_mode.get(),
                "used_base_palette": self.used_base_palette.get(),
            }

            data_needed_for_processing = (
                input_folder,
                self.sg_images_dict,
                self.sg_shared_palette,
                self.sg_max_colors_used,
                self.sg_image_height,
                self.sg_image_width,
                self.sg_available_frames,
                min_row_column_density,
                displace_sprite,
                animation_group,
                scan_chunk_sizes,
                intra_scan,
                inter_scan,
                export_as_wan,
                sprite_category,
                custom_properties,
            )

            generate_sprite_main(data_needed_for_processing)

        except Exception as e:
            print(f"\n[ERROR] Error during generation:\n{str(e)}")

        finally:
            self.enable_ui_after_processing(0)  # Tab 0 = Sprite Generator

    def prepare_validation_data(
        self,
        tab_index: int,
        input_path: Path,
        validation_thread_func,
        reset_data=True,
    ):
        self.disable_ui_for_processing(tab_index)

        # Reset validation data based on tab
        if tab_index == 1 and reset_data:  # Frames Generator
            self.fg_sprite = None
            self.fg_input_path = None
            self.fg_validation_info = {}
            self.fg_base_validation_info = {}
        elif tab_index == 2:  # Wan IO
            self.wan_io_sprite = None
            self.wan_io_input_path = None
            self.wan_io_is_folder = False
            # Reset buttons to disabled state
            self.wan_io_extract_btn.config(state="disabled")
            self.wan_io_generate_btn.config(state="disabled")

        if not input_path.exists():
            self.enable_ui_after_processing(tab_index)
            return

        self.clear_console()

        thread = threading.Thread(target=validation_thread_func, args=(input_path,))
        thread.daemon = True
        thread.start()

    def validate_frames_generator_thread(self, input_path: Path, target="main"):
        sprite = None
        validation_info = {}

        def complete_validation():
            if sprite:
                if target == "main":
                    self.fg_sprite = sprite
                    self.fg_input_path = input_path
                    self.fg_validation_info = validation_info

                    # Warn if base sprite is needed but not provided
                    requires_base_sprite = validation_info.get("requires_base_sprite")
                    if requires_base_sprite and self.fg_base_sprite is None:
                        base_name, hint = BASE_SPRITE_INFO.get(
                            requires_base_sprite, (requires_base_sprite, "")
                        )
                        print(
                            f"[WARNING] Needs {base_name} base sprite — frames may be incomplete without it."
                        )
                        if hint:
                            print(f"[HINT] The {base_name} base is the {hint}.\n")
                    # Check if already-loaded base sprite is the correct type
                    elif requires_base_sprite and self.fg_base_sprite is not None:
                        base_type = self.fg_base_validation_info.get("base_type")
                        if base_type != requires_base_sprite:
                            expected_name, hint = BASE_SPRITE_INFO.get(
                                requires_base_sprite, (requires_base_sprite, "")
                            )
                            loaded_name, _ = (
                                BASE_SPRITE_INFO.get(base_type, ("not a base file", ""))
                                if base_type
                                else ("not a base file", "")
                            )
                            print(
                                f"[WARNING] Expected {expected_name} base sprite — loaded base is {loaded_name}."
                            )
                            if hint:
                                print(
                                    f"[HINT] The {expected_name} base is the {hint}.\n"
                                )
                    # Always enable generate button
                    self.root.after(
                        0, lambda: self.generate_frames_btn.config(state="normal")
                    )
                else:  # target == "base"
                    self.fg_base_sprite = sprite
                    self.fg_base_validation_info = validation_info
                    base_type = validation_info.get("base_type")

                    # If main sprite is loaded, check compatibility
                    if self.fg_sprite:
                        requires_base_sprite = self.fg_validation_info.get(
                            "requires_base_sprite"
                        )
                        if requires_base_sprite and base_type != requires_base_sprite:
                            expected_name, hint = BASE_SPRITE_INFO.get(
                                requires_base_sprite, (requires_base_sprite, "")
                            )
                            loaded_name, _ = (
                                BASE_SPRITE_INFO.get(base_type, ("not a base file", ""))
                                if base_type
                                else ("not a base file", "")
                            )
                            print(
                                f"[WARNING] Expected {expected_name} base sprite — provided file is {loaded_name}."
                            )
                            if hint:
                                print(
                                    f"[HINT] The {expected_name} base is the {hint}.\n"
                                )
                        # Enable generate button
                        self.root.after(
                            0, lambda: self.generate_frames_btn.config(state="normal")
                        )
                    else:
                        # No main sprite yet - just show info about what type of base was loaded
                        if base_type:
                            base_name, _ = BASE_SPRITE_INFO.get(
                                base_type, (base_type, "")
                            )
                            print(
                                f"[INFO] Loaded {base_name} base sprite. Select a main sprite to continue.\n"
                            )
                        else:
                            print("[WARNING] This file is not a valid base sprite.\n")
                            hint_lines = [
                                f"  • {name} base — {loc}"
                                for name, loc in BASE_SPRITE_INFO.values()
                            ]
                            print(
                                "[HINT] Valid base sprites are:\n"
                                + "\n".join(hint_lines)
                                + "\n"
                            )
                print(
                    f"[OK] {'Main' if target == 'main' else 'Base'} sprite loaded: {input_path}"
                )

        try:
            sprite, validation_info = validate_external_input(
                input_path, raise_on_errors=False
            )
        except Exception as e:
            print(f"[ERROR] Validation error:\n{str(e)}")
        finally:
            self.root.after(0, complete_validation)
            self.enable_ui_after_processing(
                1, enable_action_buttons=False
            )  # Tab 1 = Frames Generator (action button enabled conditionally)

    def generate_frames(self):
        self.clear_console()
        self.disable_ui_for_processing(1)  # Tab 1 = Frames Generator
        thread = threading.Thread(target=self.generate_frames_thread)
        thread.daemon = True
        thread.start()

    def generate_frames_thread(self):
        try:
            if self.fg_sprite is None or self.fg_input_path is None:
                print(
                    "[ERROR] No valid input selected. Please select a folder or WAN file first."
                )
                return

            avoid_overlap = self.avoid_overlap.get()

            data_needed_for_processing = (
                self.fg_sprite,
                self.fg_base_sprite,
                self.fg_input_path,
                avoid_overlap,
                self.fg_validation_info,
                self.fg_base_validation_info,
            )
            generate_frames_main(data_needed_for_processing)

        except Exception as e:
            print(f"\n[ERROR] Error during generation:\n{str(e)}")

        finally:
            self.enable_ui_after_processing(1)  # Tab 1 = Frames Generator

    def validate_wan_io_thread(self, input_path: Path):
        sprite = None
        wan_io_is_folder = input_path.is_dir()

        def complete_validation():
            if sprite is not None:
                self.wan_io_sprite = sprite
                self.wan_io_input_path = input_path
                self.wan_io_is_folder = wan_io_is_folder

                # Enable the appropriate button based on input type
                if self.wan_io_is_folder:
                    self.root.after(
                        0,
                        lambda: self.wan_io_generate_btn.config(state="normal"),
                    )
                    self.root.after(
                        0,
                        lambda: self.wan_io_extract_btn.config(state="disabled"),
                    )
                    print("[OK] Validation Successful. Ready to generate WAN file.")
                else:
                    self.root.after(
                        0,
                        lambda: self.wan_io_extract_btn.config(state="normal"),
                    )
                    self.root.after(
                        0,
                        lambda: self.wan_io_generate_btn.config(state="disabled"),
                    )
                    print("[OK] Validation Successful. Ready to extract WAN file.")

        try:
            if wan_io_is_folder:
                # Generating WAN: raise on errors
                sprite, _ = validate_external_input(input_path, raise_on_errors=True)
            else:
                # Extracting WAN: allow errors so user can fix the extracted files
                sprite, _ = validate_external_input(input_path, raise_on_errors=False)
        except Exception as e:
            print(f"[ERROR] Validation error:\n{str(e)}")
        finally:
            self.root.after(0, complete_validation)
            self.enable_ui_after_processing(
                2, enable_action_buttons=False
            )  # Tab 2 = Wan IO (action buttons enabled conditionally)

    def process_wan_io(self):
        self.clear_console()
        self.disable_ui_for_processing(2)  # Tab 2 = Wan IO
        thread = threading.Thread(target=self.process_wan_io_thread)
        thread.daemon = True
        thread.start()

    def process_wan_io_thread(self):
        try:
            if self.wan_io_sprite is None or self.wan_io_input_path is None:
                print(
                    "[ERROR] No valid input selected. Please select a folder or WAN file first."
                )
                return

            data = (self.wan_io_sprite, self.wan_io_input_path)
            wan_transform_main(data)

        except Exception as e:
            print(f"\n[ERROR] Error during processing:\n{str(e)}")

        finally:
            self.enable_ui_after_processing(2)  # Tab 2 = Wan IO

    def redirect_stdout_to_console(self):
        stdout_queue = self.stdout_queue
        root = self.root
        processor_event = self._stdout_processor_scheduled

        def schedule_processing():
            if not processor_event.is_set():
                processor_event.set()
                root.after(0, self._process_stdout_queue)

        class StdoutWriter:
            def __init__(self, queue_ref, schedule_fn):
                self.queue = queue_ref
                self.schedule = schedule_fn

            def write(self, text):
                if text:
                    try:
                        self.queue.put_nowait(text)
                        self.schedule()
                    except queue.Full:
                        try:
                            self.queue.get_nowait()
                            self.queue.put_nowait(text)
                            self.schedule()
                        except queue.Empty:
                            pass
                    except Exception:
                        pass

            def flush(self):
                self.schedule()

        sys.stdout = StdoutWriter(stdout_queue, schedule_processing)

    def _process_stdout_queue(self):
        self._stdout_processor_scheduled.clear()
        messages = []
        max_batch_size = 50
        max_chars = 5000

        try:
            char_count = 0
            while len(messages) < max_batch_size and char_count < max_chars:
                text = self.stdout_queue.get_nowait()
                messages.append(text)
                char_count += len(text)
        except queue.Empty:
            pass

        if messages:
            combined_text = "".join(messages)
            try:
                self.console_text.config(state="normal")
                self.console_text.insert(tk.END, combined_text)
                self.console_text.see(tk.END)
                self.console_text.config(state="disabled")
            except tk.TclError:
                pass

        if not self.stdout_queue.empty():
            self._stdout_processor_scheduled.set()
            self.root.after(10, self._process_stdout_queue)


# ----------------Entry Point----------------

if __name__ == "__main__":
    root = tk.Tk()
    WanimationStudioGUI(root)
    root.mainloop()
