import json
import tkinter as tk
import urllib.request
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from typing import Optional

from bin_pack import (
    PackManager,
    KNOWN_PACK_FILES,
    detect_type,
    type_to_ext,
    format_size,
)
from icons.data import SMALL_ICON_DATA, LARGE_ICON_DATA
from data.config import DEBUG, CURRENT_VERSION, RELEASE_API_ENDPOINT


class PackExplorer:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Pack Explorer")
        self.root.geometry("700x600")
        self.root.minsize(700, 600)

        small_icon = tk.PhotoImage(data=SMALL_ICON_DATA)
        large_icon = tk.PhotoImage(data=LARGE_ICON_DATA)
        self.root.iconphoto(True, small_icon, large_icon)

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self.manager = PackManager()

        self._build_ui()
        self.check_for_update()

    def _build_ui(self):
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        main = ttk.Frame(self.root, padding=10)
        main.grid(row=0, column=0, sticky="nsew")
        main.columnconfigure(0, weight=1)
        main.rowconfigure(3, weight=1)

        self._build_file_section(main, row=0)
        self._build_pack_section(main, row=1)
        self._build_info_section(main, row=2)
        self._build_list_section(main, row=3)
        self._build_button_section(main, row=4)
        self._build_status_section(main, row=5)

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
        ).grid(row=0, column=2, padx=(10, 0))

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
        self.tree.delete(*self.tree.get_children())
        for idx, data in enumerate(self.manager):
            etype = detect_type(data)
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

        etype, _ = self.manager.get_entry_info(idx)
        ext = type_to_ext(etype)

        path = filedialog.asksaveasfilename(
            title=f"Export entry {idx:04d}",
            initialfile=f"entry_{idx:04d}{ext}",
            defaultextension=ext,
            filetypes=[(f"{etype} files", f"*{ext}"), ("All files", "*.*")],
        )
        if path:
            try:
                self.manager.export_entry(idx, Path(path))
                self._set_status(f"Exported entry {idx:04d} to {Path(path).name}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to export:\n{e}")

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
                self.manager.import_entry(idx, Path(path))
                self._refresh_list()

                for item in self.tree.get_children():
                    if self.tree.item(item)["values"][0] == f"{idx:04d}":
                        self.tree.selection_set(item)
                        break

                self._set_status(f"Imported {Path(path).name} to entry {idx:04d}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to import:\n{e}")

    def _on_import_all(self):
        directory = filedialog.askdirectory(title="Create pack from folder")
        if not directory:
            return

        try:
            old_header_len = None
            old_loaded_data = self.manager._loaded_data
            old_rom = self.manager.rom
            old_file_path = self.manager.file_path
            old_pack_path = self.manager.pack_path
            if self.manager.pack is not None:
                old_header_len = self.manager.pack._header_len

            self.manager.create_new()
            count = self.manager.import_all(Path(directory))

            if count == 0:
                messagebox.showinfo("Info", "No files found in directory")
                return

            if old_header_len is not None:
                self.manager.pack._header_len = old_header_len
            self.manager._loaded_data = old_loaded_data
            self.manager.rom = old_rom
            self.manager.file_path = old_file_path
            self.manager.pack_path = old_pack_path

            self._refresh_list()
            self._set_status(
                f"Created pack with {count} entries from {Path(directory).name}/"
            )
        except Exception as e:
            messagebox.showerror("Error", f"Failed to import:\n{e}")

    def _on_export_all(self):
        if not self.manager.pack:
            messagebox.showwarning("Warning", "No file loaded")
            return

        directory = filedialog.askdirectory(title="Export all entries to folder")
        if not directory:
            return

        try:
            count = self.manager.export_all(Path(directory))
            self._set_status(f"Exported {count} entries to {Path(directory).name}/")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to export:\n{e}")

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
