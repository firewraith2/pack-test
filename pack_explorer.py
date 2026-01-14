import json
import numpy as np
import threading
import tkinter as tk
import urllib.request
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from typing import Optional, List
from PIL import Image, ImageTk
from bin_pack import (
    PackManager,
    KNOWN_PACK_FILES,
    detect_type,
    detect_inner_type,
    type_to_ext,
    format_size,
)
from icons.data import SMALL_ICON_DATA, LARGE_ICON_DATA
from data.config import DEBUG, CURRENT_VERSION, RELEASE_API_ENDPOINT

# Optional WAN preview support - gracefully handle missing generators module
try:
    from generators import generate_frames_main, validate_external_input

    WAN_PREVIEW_AVAILABLE = True
except ImportError:
    WAN_PREVIEW_AVAILABLE = False


def generate_wan_frames(
    raw_data: bytes, pack_manager=None, entry_index: int = 0
) -> tuple:
    """Generate preview frames from WAN data.

    Args:
        raw_data: Raw WAN file bytes
        pack_manager: Optional PackManager for base sprite lookup
        entry_index: Index of entry being previewed

    Returns:
        Tuple of (frames: List[Image.Image], info_text: str) or (None, error_text)
    """
    if not WAN_PREVIEW_AVAILABLE:
        return None, "Preview unavailable"
    # Validate main sprite
    try:
        sprite, validation_info = validate_external_input(
            raw_data, raise_on_errors=False
        )
    except Exception as e:
        print(f"[ERROR] Validation failed: {e}")
        return None, "Error loading"

    # Determine and validate base sprite if needed
    base_sprite = None
    base_validation_info = None
    base_idx = None
    if pack_manager is not None and pack_manager.pack is not None:
        try:
            base_type = validation_info.get("base_type")
            requires_base = validation_info.get("requires_base_sprite")
            pack_len = len(pack_manager.pack)
            last_idx = pack_len - 1

            base_raw_data = None

            # Base sprites need their complementary base
            if base_type == "animation" and entry_index != last_idx:
                base_raw_data = pack_manager.pack[last_idx]
                base_idx = last_idx
            elif base_type == "image" and entry_index != 0:
                base_raw_data = pack_manager.pack[0]
                base_idx = 0
            # Non-base sprites may need a base for shared palette
            elif requires_base == "image" and entry_index != last_idx:
                base_raw_data = pack_manager.pack[last_idx]
                base_idx = last_idx
            elif requires_base == "animation" and entry_index != 0:
                base_raw_data = pack_manager.pack[0]
                base_idx = 0
            elif requires_base == "4bpp" and entry_index != 1 and pack_len > 1:
                base_raw_data = pack_manager.pack[1]
                base_idx = 1

            if base_raw_data is not None:
                base_sprite, base_validation_info = validate_external_input(
                    base_raw_data, raise_on_errors=False
                )

        except Exception as e:
            print(f"[WARNING] Could not load base sprite: {e}")

    # Build info text
    input_str = f"{entry_index:04d}"
    base_str = f"{base_idx:04d}" if base_idx is not None else "None"
    info_text = f"Input: {input_str}   Base: {base_str}"

    # Generate frames
    try:
        data = (
            sprite,
            base_sprite,
            None,  # No output folder
            "none",  # avoid_overlap
            validation_info,
            base_validation_info,
        )

        all_layers_list, global_palette = generate_frames_main(data)

        if all_layers_list is None:
            return None, "Error loading"

        # Composite layers into frame images
        frames = []
        for layers_list in all_layers_list:
            composite = _composite_layers(layers_list, global_palette)
            if composite:
                frames.append(composite)

        return frames, info_text

    except Exception as e:
        print(f"[ERROR] Frame generation failed: {e}")
        return None, "Error"


def _composite_layers(layers_list: List, palette: np.ndarray) -> Optional[Image.Image]:
    """Composite frame layers into single RGBA image."""
    if not layers_list:
        return None

    composite = None

    for layer_array, mask, palette_slot in layers_list:
        layer_img = Image.fromarray(layer_array, mode="P")
        layer_img.putpalette(palette)
        layer_img.info["transparency"] = 0
        rgba_layer = layer_img.convert("RGBA")

        if composite is None:
            composite = rgba_layer
        else:
            composite = Image.alpha_composite(composite, rgba_layer)

    return composite


class PreviewPanel:
    """Generic preview panel for animated frame sequences."""

    def __init__(self, parent: ttk.Frame):
        self.parent = parent
        self.frame_images = []  # List of PhotoImage
        self.current_frame_index = 0
        self.after_id = None
        self.frame_duration = 100  # milliseconds

        self._build_ui()

    def _build_ui(self):
        """Build the preview UI."""
        # Info label at top
        self.info_label = ttk.Label(
            self.parent, text="Input: None   Base: None", anchor="center"
        )
        self.info_label.pack(fill="x", padx=5, pady=(5, 0))

        # Canvas for display
        self.canvas = tk.Canvas(
            self.parent,
            width=150,
            height=150,
            bg="#2b2b2b",
            highlightthickness=0,
        )
        self.canvas.pack(fill="both", expand=True, padx=5, pady=5)

        # Control frame
        control_frame = ttk.Frame(self.parent)
        control_frame.pack(fill="x", padx=5, pady=(0, 5))

        # Status label
        self.status_label = ttk.Label(control_frame, text="No preview", anchor="w")
        self.status_label.pack(side="left", fill="x", expand=True)

        # Toggle BG button
        self.bg_is_dark = True
        ttk.Button(control_frame, text="Toggle BG", command=self._toggle_bg).pack(
            side="right"
        )

    def _toggle_bg(self):
        """Toggle background color."""
        self.bg_is_dark = not self.bg_is_dark
        new_bg = "#2b2b2b" if self.bg_is_dark else "#f0f0f0"
        self.canvas.config(bg=new_bg)

    def load_frames(self, frames: List[Image.Image], info_text: str = ""):
        """Load and display frame images.

        Args:
            frames: List of PIL Image objects
            info_text: Optional info text to display at top
        """
        self._stop_animation()
        self.frame_images = []
        self.current_frame_index = 0

        self.info_label.config(text=info_text)

        if not frames:
            self.status_label.config(text="No frames")
            return

        # Convert to PhotoImage
        for frame in frames:
            self.frame_images.append(ImageTk.PhotoImage(frame))

        # Resize canvas to first frame
        img = self.frame_images[0]
        self.canvas.config(width=img.width(), height=img.height())
        self.status_label.config(text=f"{len(self.frame_images)} frames")
        self._start_animation()

    def _start_animation(self):
        """Start animation loop."""
        if not self.frame_images:
            return
        self._display_frame()
        self._schedule_next()

    def _stop_animation(self):
        """Stop animation loop."""
        if self.after_id:
            self.parent.after_cancel(self.after_id)
            self.after_id = None

    def _display_frame(self):
        """Display current frame."""
        if not self.frame_images:
            return

        img = self.frame_images[self.current_frame_index]
        self.canvas.delete("all")
        self.canvas.create_image(
            self.canvas.winfo_width() // 2,
            self.canvas.winfo_height() // 2,
            image=img,
            anchor="center",
        )
        self.status_label.config(
            text=f"Frame {self.current_frame_index + 1}/{len(self.frame_images)}"
        )

    def _schedule_next(self):
        """Schedule next frame."""
        if not self.frame_images:
            return
        self.current_frame_index = (self.current_frame_index + 1) % len(
            self.frame_images
        )
        self.after_id = self.parent.after(self.frame_duration, self._animate)

    def _animate(self):
        """Animation tick."""
        self._display_frame()
        self._schedule_next()

    def clear(self):
        """Clear the preview."""
        self._stop_animation()
        self.frame_images = []
        self.canvas.delete("all")
        self.status_label.config(text="No preview")
        self.info_label.config(text="Input: None   Base: None")


class PackExplorer:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Pack Explorer")
        self.root.geometry("1050x600")

        small_icon = tk.PhotoImage(data=SMALL_ICON_DATA)
        large_icon = tk.PhotoImage(data=LARGE_ICON_DATA)
        self.root.iconphoto(True, small_icon, large_icon)

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self.manager = PackManager()

        # Cache for decompressed PKDPX data (idx, decompressed_data)
        self._pkdpx_cache = (None, None)
        self._last_previewed_idx = None  # Track to avoid redundant preview

        self._build_ui()
        self.check_for_update()

    def _build_ui(self):
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        # Top-level PanedWindow: controls on left, preview on right
        # Switched to tk.PanedWindow for better minsize support
        paned = tk.PanedWindow(self.root, orient=tk.HORIZONTAL, sashwidth=10)
        paned.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

        # Left pane: All controls
        controls = ttk.Frame(paned)
        controls.columnconfigure(0, weight=1)
        controls.rowconfigure(3, weight=1)  # List section expands
        paned.add(controls, minsize=650)

        self._build_file_section(controls, row=0)
        self._build_pack_section(controls, row=1)
        self._build_info_section(controls, row=2)
        self._build_list_section(controls, row=3)
        self._build_button_section(controls, row=4)
        self._build_status_section(controls, row=5)

        # Right pane: Preview
        preview_frame = ttk.LabelFrame(paned, text="Preview", padding=5)
        self.preview_panel = PreviewPanel(preview_frame)
        paned.add(preview_frame, minsize=400)

    def _build_file_section(self, parent: ttk.Frame, row: int):
        frame = ttk.LabelFrame(parent, text="File", padding=5)
        frame.grid(row=row, column=0, sticky="ew", pady=(0, 5))
        frame.columnconfigure(0, weight=1)

        self.file_entry = ttk.Entry(frame, state="readonly")
        self.file_entry.grid(row=0, column=0, sticky="ew", padx=(0, 5))

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=0, column=1, sticky="e")

        ttk.Button(btn_frame, text="Browse", command=self._on_browse).grid(
            row=0, column=0
        )
        ttk.Button(btn_frame, text="Save", command=self._on_save).grid(
            row=0, column=1, padx=5
        )
        ttk.Button(btn_frame, text="Save As", command=self._on_save_as).grid(
            row=0, column=2
        )

    def _build_pack_section(self, parent: ttk.Frame, row: int):
        frame = ttk.Frame(parent)
        frame.grid(row=row, column=0, sticky="ew", pady=(0, 5))
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="Pack:").grid(row=0, column=0, sticky="w")

        self.pack_combo = ttk.Combobox(frame, values=KNOWN_PACK_FILES, state="disabled")
        self.pack_combo.set(KNOWN_PACK_FILES[0])
        self.pack_combo.grid(row=0, column=1, sticky="ew", padx=(5, 0))
        self.pack_combo.bind("<<ComboboxSelected>>", self._on_pack_changed)

        self.advanced_mode = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            frame,
            text="Advanced Mode",
            variable=self.advanced_mode,
            command=self._on_advanced_mode_toggle,
        ).grid(row=0, column=3, padx=(10, 0))

        # PKDPX compress/decompress checkbox (always visible)
        self.handle_compression = tk.BooleanVar(value=False)
        self.pkdpx_check = ttk.Checkbutton(
            frame, text="PKDPX", variable=self.handle_compression
        )
        self.pkdpx_check.grid(row=0, column=2, padx=(5, 0))

    def _build_info_section(self, parent: ttk.Frame, row: int):
        frame = ttk.LabelFrame(parent, text="Pack Info", padding=5)
        frame.grid(row=row, column=0, sticky="ew", pady=(0, 5))

        ttk.Label(frame, text="Loaded:").grid(row=0, column=0, sticky="w")
        self.loaded_md5 = ttk.Label(frame, text="-")
        self.loaded_md5.grid(row=0, column=1, sticky="w", padx=(10, 20))
        self.loaded_size = ttk.Label(frame, text="-")
        self.loaded_size.grid(row=0, column=2, sticky="w")

        ttk.Label(frame, text="Current:").grid(row=1, column=0, sticky="w")
        self.current_md5 = ttk.Label(frame, text="-")
        self.current_md5.grid(row=1, column=1, sticky="w", padx=(10, 20))
        self.current_size = ttk.Label(frame, text="-")
        self.current_size.grid(row=1, column=2, sticky="w")

    def _build_list_section(self, parent: ttk.Frame, row: int):
        frame = ttk.LabelFrame(parent, text="Pack Contents", padding=5)
        frame.grid(row=row, column=0, sticky="nsew", pady=(0, 5))
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        columns = ("index", "type", "size")
        self.tree = ttk.Treeview(
            frame, columns=columns, show="headings", selectmode="browse"
        )
        self.tree.heading("index", text="Index")
        self.tree.heading("type", text="Type")
        self.tree.heading("size", text="Size (bytes)")
        self.tree.column("index", minwidth=200, anchor="center")
        self.tree.column("type", minwidth=200, anchor="center")
        self.tree.column("size", minwidth=200, anchor="center")
        self.tree.tag_configure("modified", foreground="blue")
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)

        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scrollbar.set)

    def _build_button_section(self, parent: ttk.Frame, row: int):
        frame = ttk.Frame(parent)
        frame.grid(row=row, column=0, sticky="ew", pady=(10, 15))
        frame.columnconfigure(0, weight=1)

        # Row 0: Main buttons
        row0 = ttk.Frame(frame)
        row0.grid(row=0, column=0, sticky="ew")
        row0.columnconfigure(1, weight=1)

        left = ttk.Frame(row0)
        left.grid(row=0, column=0, sticky="w")

        ttk.Button(left, text="Export Selected", command=self._on_export_selected).grid(
            row=0, column=0
        )
        ttk.Button(
            left, text="Import to Selected", command=self._on_import_selected
        ).grid(row=0, column=1, padx=5)

        self.advanced_frame = ttk.Frame(left)
        ttk.Button(
            self.advanced_frame, text="Add Entry", command=self._on_add_entry
        ).grid(row=0, column=0, padx=(5, 0))
        ttk.Button(
            self.advanced_frame, text="Remove Entry", command=self._on_remove_entry
        ).grid(row=0, column=1, padx=5)

        right = ttk.Frame(row0)
        right.grid(row=0, column=2, sticky="e")

        self.import_all_btn = ttk.Button(
            right, text="Import All", command=self._on_import_all
        )

        ttk.Button(right, text="Export All", command=self._on_export_all).grid(
            row=0, column=1
        )

    def _on_advanced_mode_toggle(self):
        if self.advanced_mode.get():
            if not messagebox.askokcancel(
                "Warning",
                "Advanced Mode enables options that can break the game.\n\n"
                "Only enable if you know what you're doing.",
                icon="warning",
            ):
                self.advanced_mode.set(False)
                return
            self.advanced_frame.grid(row=0, column=2)
            self.import_all_btn.grid(row=0, column=0, padx=(0, 5))
        else:
            self.advanced_frame.grid_remove()
            self.import_all_btn.grid_remove()

    def _build_status_section(self, parent: ttk.Frame, row: int):
        frame = ttk.Frame(parent)
        frame.grid(row=row, column=0, sticky="ew")
        frame.columnconfigure(0, weight=1)

        self.status = ttk.Label(
            frame, text="Ready", relief="sunken", anchor="w", padding=(5, 2)
        )
        self.status.grid(row=0, column=0, sticky="ew")

        version_label = ttk.Label(frame, text=f"v{CURRENT_VERSION}", foreground="gray")
        version_label.grid(row=0, column=1, padx=(5, 0))

    def _set_file_entry(self, text: str):
        self.file_entry.config(state="normal")
        self.file_entry.delete(0, "end")
        self.file_entry.insert(0, text)
        self.file_entry.config(state="readonly")

    def _set_status(self, message: str):
        self.status.config(text=message)
        self.root.update_idletasks()

    def _clear_ui(self):
        self.manager = PackManager()
        self._set_file_entry("")
        self.loaded_md5.config(text="-")
        self.loaded_size.config(text="-")
        self.current_md5.config(text="-", foreground="")
        self.current_size.config(text="-", foreground="")
        self.pack_combo.config(state="disabled")
        self.tree.delete(*self.tree.get_children())

    def _refresh_list(self):
        # Invalidate caches when pack contents change
        self._pkdpx_cache = (None, None)
        self._last_previewed_idx = None

        self.tree.delete(*self.tree.get_children())
        for idx, data in enumerate(self.manager):
            etype = detect_type(data)  # Fast - no decompression
            tags = ("modified",) if idx in self.manager.modified_indices else ()
            self.tree.insert(
                "", "end", values=(f"{idx:04d}", etype, f"{len(data):,}"), tags=tags
            )
        self._update_checksums()

    def _update_checksums(self):
        self.loaded_md5.config(text=self.manager.get_loaded_checksum())
        self.loaded_size.config(text=format_size(self.manager.get_loaded_size()))
        self.current_md5.config(text=self.manager.get_current_checksum())
        self.current_size.config(text=format_size(self.manager.get_current_size()))

        color = "blue" if self.manager.modified else ""
        self.current_md5.config(foreground=color)
        self.current_size.config(foreground=color)

    def _get_selected_index(self) -> Optional[int]:
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("Warning", "No entry selected")
            return None
        item = self.tree.item(selection[0])
        return int(item["values"][0])

    def _on_browse(self):
        filetypes = [
            ("NDS ROMs & Pack files", "*.nds *.bin"),
            ("All files", "*.*"),
        ]
        path = filedialog.askopenfilename(
            title="Open pack file or NDS ROM", filetypes=filetypes
        )
        if not path:
            return

        path = Path(path)
        try:
            if path.suffix.lower() == ".nds":
                pack_path = self.pack_combo.get()
                count = self.manager.load_from_rom(path, pack_path)
                self.pack_combo.config(state="readonly")
                self._set_status(f"Loaded {count} entries from ROM: {path.name}")
            else:
                count = self.manager.load_from_file(path)
                self.pack_combo.config(state="disabled")
                self._set_status(f"Loaded {count} entries from {path.name}")

            self._set_file_entry(str(path))
            self._refresh_list()

        except Exception as e:
            self._clear_ui()
            self._set_status(f"Error: {e}")

    def _on_pack_changed(self, event=None):
        if not self.manager.rom:
            return

        new_path = self.pack_combo.get()
        if new_path == self.manager.pack_path:
            return

        if self.manager.modified:
            if not messagebox.askyesno(
                "Unsaved Changes", "You have unsaved changes. Switch anyway?"
            ):
                self.pack_combo.set(self.manager.pack_path)
                return

        try:
            count = self.manager.switch_pack(new_path)
            self._refresh_list()
            self._set_status(f"Loaded {count} entries from {new_path}")
        except KeyError:
            self._set_status(f"Error: {new_path} not found in ROM")
            self.pack_combo.set(self.manager.pack_path)
        except Exception as e:
            self._set_status(f"Error: {e}")
            self.pack_combo.set(self.manager.pack_path)

    def _on_save(self):
        if not self.manager.pack:
            messagebox.showwarning("Warning", "No file loaded")
            return

        try:
            self.manager.save()
            self._refresh_list()
            self._set_status(f"Saved to {self.manager.file_path.name}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save:\n{e}")

    def _on_save_as(self):
        if not self.manager.pack:
            messagebox.showwarning("Warning", "No file loaded")
            return

        if self.manager.rom:
            filetypes = [("NDS ROMs", "*.nds"), ("BIN files", "*.bin"), ("All", "*.*")]
            default_ext = ".nds"
        else:
            filetypes = [("BIN files", "*.bin"), ("All files", "*.*")]
            default_ext = ".bin"

        path = filedialog.asksaveasfilename(
            title="Save pack file", defaultextension=default_ext, filetypes=filetypes
        )
        if not path:
            return

        path = Path(path)
        try:
            save_rom = self.manager.rom and path.suffix.lower() == ".nds"
            self.manager.save_as(path, save_rom=save_rom)
            self._set_file_entry(str(path))
            self._refresh_list()
            self._set_status(f"Saved to {path.name}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save:\n{e}")

    def _on_export_selected(self):
        if not self.manager.pack:
            messagebox.showwarning("Warning", "No file loaded")
            return

        idx = self._get_selected_index()
        if idx is None:
            return

        data = self.manager.pack[idx]
        etype = detect_type(data)

        # For PKDPX entries, use checkbox to decide on decompression
        decompress = etype == "PKDPX" and self.handle_compression.get()
        if decompress:
            # Use cached decompressed data if available
            if self._pkdpx_cache[0] == idx and self._pkdpx_cache[1] is not None:
                export_data = self._pkdpx_cache[1]
            else:
                export_data = self.manager.get_entry_data(idx, decompress=True)
            export_type = detect_type(export_data)
        else:
            export_data = data
            export_type = etype

        ext = type_to_ext(export_type)

        path = filedialog.asksaveasfilename(
            title=f"Export entry {idx:04d}",
            initialfile=f"entry_{idx:04d}{ext}",
            defaultextension=ext,
            filetypes=[(f"{export_type} files", f"*{ext}"), ("All files", "*.*")],
        )
        if path:
            try:
                with open(path, "wb") as f:
                    f.write(export_data)
                self._set_status(f"Exported entry {idx:04d} to {Path(path).name}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to export:\n{e}")

    def _on_tree_select(self, event=None):
        """Handle tree selection - auto-preview WAN and PKDPX(WAN) files."""
        if not self.manager.pack:
            return

        selection = self.tree.selection()
        if not selection:
            self.preview_panel.clear()
            self._pkdpx_cache = (None, None)  # Clear cache
            return

        item = self.tree.item(selection[0])
        idx = int(item["values"][0])
        etype = item["values"][1]

        # Skip if same entry is already being previewed
        if idx == self._last_previewed_idx:
            return

        # Clear cache if selecting a different entry
        if self._pkdpx_cache[0] != idx:
            self._pkdpx_cache = (None, None)

        # Get WAN data for preview
        wan_data = None
        if etype == "WAN":
            try:
                wan_data = self.manager.get_entry_data(idx)
            except Exception as e:
                print(f"[ERROR] Failed to get entry data: {e}")
        elif etype == "PKDPX":
            try:
                wan_data = self.manager.get_entry_data(idx, decompress=True)
                self._pkdpx_cache = (idx, wan_data)
                if detect_type(wan_data) != "WAN":
                    wan_data = None
            except Exception as e:
                print(f"[ERROR] Failed to decompress: {e}")

        if wan_data is None:
            self.preview_panel.clear()
            self._last_previewed_idx = None
            return

        # Show loading state and generate frames in background
        self.preview_panel.info_label.config(text=f"Input: {idx:04d}   Base: ...")
        self.preview_panel.status_label.config(text="Loading...")
        self._last_previewed_idx = idx

        def generate_in_background():
            frames, info_text = generate_wan_frames(wan_data, self.manager, idx)
            # Schedule UI update on main thread
            self.root.after(0, lambda: self._on_frames_ready(idx, frames, info_text))

        thread = threading.Thread(target=generate_in_background, daemon=True)
        thread.start()

    def _on_frames_ready(self, idx: int, frames, info_text: str):
        """Callback when frames are ready from background thread."""
        # Check if user selected a different entry while loading
        if self._last_previewed_idx != idx:
            return

        if frames:
            self.preview_panel.load_frames(frames, info_text)
        else:
            self.preview_panel.clear()
            self._last_previewed_idx = None

    def _on_import_selected(self):
        if not self.manager.pack:
            messagebox.showwarning("Warning", "No file loaded")
            return

        idx = self._get_selected_index()
        if idx is None:
            return

        path = filedialog.askopenfilename(
            title=f"Import to entry {idx:04d}",
            filetypes=[("All files", "*.*")],
        )
        if path:
            try:
                with open(path, "rb") as f:
                    data = f.read()

                # Skip compression if already PKDPX, otherwise compress if checkbox checked
                is_already_pkdpx = detect_type(data) == "PKDPX"
                compress = self.handle_compression.get() and not is_already_pkdpx
                if compress:
                    status_msg = (
                        f"Imported & compressed {Path(path).name} to entry {idx:04d}"
                    )
                else:
                    status_msg = f"Imported {Path(path).name} to entry {idx:04d}"

                self.manager.import_data(idx, data, compress=compress)
                self._refresh_list()

                for item in self.tree.get_children():
                    if self.tree.item(item)["values"][0] == f"{idx:04d}":
                        self.tree.selection_set(item)
                        break

                self._set_status(status_msg)
            except Exception as e:
                messagebox.showerror("Error", f"Failed to import:\n{e}")

    def _on_import_all(self):
        directory = filedialog.askdirectory(title="Create pack from folder")
        if not directory:
            return

        # Save state before async operation
        old_header_len = None
        old_loaded_data = self.manager._loaded_data
        old_loaded_checksum = self.manager._loaded_checksum
        old_rom = self.manager.rom
        old_file_path = self.manager.file_path
        old_pack_path = self.manager.pack_path
        if self.manager.pack is not None:
            old_header_len = self.manager.pack._header_len

        self.manager.create_new()
        dir_path = Path(directory)
        compress = self.handle_compression.get()

        self._set_status(f"Importing from {dir_path.name}/...")

        def import_in_background():
            try:
                files = sorted(dir_path.iterdir())
                count = 0
                for file_path in files:
                    if file_path.is_file():
                        data = file_path.read_bytes()
                        # Skip compression if already PKDPX
                        is_already_pkdpx = detect_type(data) == "PKDPX"
                        should_compress = compress and not is_already_pkdpx
                        self.manager.add_data(data, compress=should_compress)
                        count += 1

                # Schedule UI update on main thread
                self.root.after(
                    0,
                    lambda: self._on_import_all_done(
                        count,
                        dir_path,
                        old_header_len,
                        old_loaded_data,
                        old_loaded_checksum,
                        old_rom,
                        old_file_path,
                        old_pack_path,
                    ),
                )
            except Exception as e:
                self.root.after(
                    0, lambda: messagebox.showerror("Error", f"Failed to import:\n{e}")
                )

        thread = threading.Thread(target=import_in_background, daemon=True)
        thread.start()

    def _on_import_all_done(
        self,
        count,
        dir_path,
        old_header_len,
        old_loaded_data,
        old_loaded_checksum,
        old_rom,
        old_file_path,
        old_pack_path,
    ):
        """Callback when import all completes."""
        if count == 0:
            messagebox.showinfo("Info", "No files found in directory")
            return

        if old_header_len is not None:
            self.manager.pack._header_len = old_header_len
        self.manager._loaded_data = old_loaded_data
        self.manager._loaded_checksum = old_loaded_checksum
        self.manager.rom = old_rom
        self.manager.file_path = old_file_path
        self.manager.pack_path = old_pack_path

        self._refresh_list()
        self._set_status(f"Created pack with {count} entries from {dir_path.name}/")

    def _on_export_all(self):
        if not self.manager.pack:
            messagebox.showwarning("Warning", "No file loaded")
            return

        directory = filedialog.askdirectory(title="Export all entries to folder")
        if not directory:
            return

        dir_path = Path(directory)
        decompress = self.handle_compression.get()
        pack_data = list(self.manager.pack)  # Copy to avoid threading issues

        self._set_status(f"Exporting to {dir_path.name}/...")

        def export_in_background():
            try:
                count = 0
                for idx, data in enumerate(pack_data):
                    etype, decompressed = detect_inner_type(data)

                    # Use checkbox to decide on decompression
                    export_data = data
                    export_type = etype
                    if etype.startswith("PKDPX(") and decompress:
                        export_data = decompressed
                        export_type = etype[6:-1]  # Extract inner type

                    ext = type_to_ext(export_type)
                    file_path = dir_path / f"entry_{idx:04d}{ext}"
                    file_path.write_bytes(export_data)
                    count += 1

                self.root.after(
                    0,
                    lambda: self._set_status(
                        f"Exported {count} entries to {dir_path.name}/"
                    ),
                )
            except Exception as e:
                self.root.after(
                    0, lambda: messagebox.showerror("Error", f"Failed to export:\n{e}")
                )

        thread = threading.Thread(target=export_in_background, daemon=True)
        thread.start()

    def _on_add_entry(self):
        if not self.manager.pack:
            messagebox.showwarning("Warning", "No file loaded")
            return

        file_path = filedialog.askopenfilename(title="Select file to add")
        if not file_path:
            return

        selection = self.tree.selection()
        insert_idx = None
        if selection:
            item = self.tree.item(selection[0])
            insert_idx = int(item["values"][0])

        try:
            idx = self.manager.add_entry(Path(file_path), insert_idx)
            self._refresh_list()
            self._set_status(f"Added {Path(file_path).name} at index {idx:04d}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to add entry:\n{e}")

    def _on_remove_entry(self):
        if not self.manager.pack:
            messagebox.showwarning("Warning", "No file loaded")
            return

        idx = self._get_selected_index()
        if idx is None:
            return

        try:
            self.manager.remove_entry(idx)
            self._refresh_list()
            self._set_status(f"Removed entry {idx:04d}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to remove entry:\n{e}")

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

    def _on_close(self):
        if self.manager.modified:
            if not messagebox.askyesno(
                "Unsaved Changes",
                "You have unsaved changes. Are you sure you want to exit?",
            ):
                return
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    PackExplorer(root)
    root.mainloop()
