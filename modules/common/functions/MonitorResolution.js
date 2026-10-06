.pragma library

// Mode dimensions are physical pixels; Qt/Wayland screen dimensions and
// Niri's logical rectangle include scaling and are for layout calculations.
function resolution(output, screen) {
    if (output) {
        const index = output.current_mode
        if (!Number.isInteger(index) || index < 0)
            return ""
        const mode = output.modes?.[index]
        const width = Number(mode?.width ?? 0)
        const height = Number(mode?.height ?? 0)
        return width > 0 && height > 0 ? width + "×" + height : ""
    }

    // Other compositors may not provide a mode snapshot. Use Qt's screen
    // pixel ratio rather than presenting its logical dimensions as pixels.
    const ratio = Number(screen?.devicePixelRatio ?? 1)
    const width = Math.round(Number(screen?.width ?? 0) * ratio)
    const height = Math.round(Number(screen?.height ?? 0) * ratio)
    return width > 0 && height > 0 ? width + "×" + height : ""
}
