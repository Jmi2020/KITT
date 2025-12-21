def print_short_voxel_cat():
    # The "Short & Stout" Voxel Shape
    # Tail is rear-mounted, but the horizontal span is reduced
    # for a more compact, sturdy look.
    cat_voxels = [
        "████",                             # Tail Tip
        "██████",                           # Tail Step
        "████",                             # Tail Stem
        "████          ██  ██",             # Tail + Ears
        "████          ██████",             # Tail + Head
        "████████████████████",             # Body Top
        "████████████████████",             # Body Mid
        "████████████████████",             # Body Low
        "  ████      ████    ",             # Legs Top
        "  ████      ████    "              # Legs Bottom
    ]

    # Gradient: Electric Cyan -> Hot Pink
    start_color = (40, 230, 255)
    end_color   = (255, 60, 180)

    def interpolate(start, end, step, total_steps):
        if total_steps <= 0: return start
        r = start[0] + (end[0] - start[0]) * step / total_steps
        g = start[1] + (end[1] - start[1]) * step / total_steps
        b = start[2] + (end[2] - start[2]) * step / total_steps
        return int(r), int(g), int(b)

    RESET = "\033[0m"
    total_lines = len(cat_voxels)

    print("\n")
    for i, line in enumerate(cat_voxels):
        r, g, b = interpolate(start_color, end_color, i, total_lines - 1)
        color_code = f"\033[38;2;{r};{g};{b}m"
        print(f"   {color_code}{line}{RESET}")
    print("\n")

if __name__ == "__main__":
    print_short_voxel_cat()