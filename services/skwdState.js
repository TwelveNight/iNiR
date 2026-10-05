.pragma library

// skwd-walld owns the desktop; no private Shell path substitutes for its reply.
function outputs(value) {
    if (!value || !value.outputs) return [];
    if (Array.isArray(value.outputs)) return value.outputs.filter(o => o && o.connected !== false);
    return Object.keys(value.outputs).map(name => Object.assign({ name: name }, value.outputs[name]))
        .filter(o => o.connected !== false);
}

function outputFor(value, monitor) {
    const list = outputs(value);
    return list.find(o => (o.name || o.output || o.output_name) === monitor) || list[0] || null;
}

function wallpaperPath(value, monitor, cacheHome) {
    const output = outputFor(value, monitor);
    if (!output) return "";
    if (output.type === "we") {
        return output.thumbnailPath || output.thumb || (output.we_id
            ? cacheHome + "/skwd-wall-v2/we-thumbs/" + output.we_id + ".webp" : "");
    }
    return String(output.path || output.current || "");
}

function applyCommand(path, monitor) {
    const command = ["skwd-helm", "apply", path];
    if (monitor) command.push("-o", monitor);
    return command;
}
