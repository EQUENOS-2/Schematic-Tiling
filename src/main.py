from tkinter import Tk
from tkinter.ttk import Button, Entry, Frame, Label

from tiling import TilingTree


class UI:
    tiler: TilingTree
    root: Tk
    width_entry: Entry
    length_entry: Entry | None
    result_label: Label

    def __init__(self):
        self.tiler = TilingTree()
        self.root = Tk()

        self.root.title("Tiling Script")
        self.root.geometry("320x220")

        self._setup()

    def _setup(self) -> None:
        instruction_label = Label(
            self.root, text="Input the size of the build (in blocks)"
        )
        instruction_label.pack(pady=10)

        input_frame = Frame(self.root)
        input_frame.pack(pady=5)

        Label(input_frame, text="Width:").grid(
            row=0, column=0, padx=5, pady=5, sticky="e"
        )
        self.width_entry = Entry(input_frame)
        self.width_entry.grid(row=0, column=1, padx=5, pady=5)

        if self.tiler.needs_length():
            Label(input_frame, text="Length:").grid(
                row=1, column=0, padx=5, pady=5, sticky="e"
            )
            self.length_entry = Entry(input_frame)
            self.length_entry.grid(row=1, column=1, padx=5, pady=5)
        else:
            self.length_entry = None

        apply_button = Button(self.root, text="Apply", command=self.apply_values)
        apply_button.pack(pady=10)

        self.result_label = Label(self.root, text="")
        self.result_label.pack(pady=5)

    def apply_values(self):
        width = self.width_entry.get()
        length = self.length_entry.get() if self.length_entry else None

        try:
            width_val = int(width)
            length_val = 0 if length is None else int(length)
            if width_val <= 0 or length_val <= 0 and length is not None:
                raise ValueError("Values must be positive")

            self.width_entry.config(state="disabled")
            if self.length_entry:
                self.length_entry.config(state="disabled")
            self.result_label.config(
                text=f"Generating {width_val}x{length_val} schematic...",
                foreground="green",
                state="disabled",
            )
            self.root.update()
            schem = self.tiler.generate_schematic(width_val, length_val)
            schem.save(f"{schem.name}.litematic")
            self.root.destroy()

        except ValueError:
            self.result_label.config(
                text="Please enter valid positive numbers", foreground="red"
            )
        except AssertionError as err:
            self.result_label.config(text=str(err), foreground="red")

    def run(self) -> None:
        self.root.mainloop()


if __name__ == "__main__":
    UI().run()
