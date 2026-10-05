#!/usr/bin/env python3
"""Merge generated colors into shared app files without replacing preferences."""
import os
import json
from pathlib import Path
import re
import sys
import tempfile

SECTION_HEADER = re.compile(r"\s*\[([^]]+)\]\s*(?:[#;].*)?$")


def merge_ini(current, generated, kind):
    # Only palette-related keys are owned here. Preserve comments, every other
    # key, and the user's theme/font/icon/application settings byte for byte.
    section = ""
    changes = {}
    for line in generated.splitlines():
        match = SECTION_HEADER.match(line)
        if match:
            section = match[1]
        elif "=" in line and not line.lstrip().startswith(("#", ";")):
            key = line.split("=", 1)[0].strip()
            allowed = ((section.startswith(("Colors:", "ColorEffects:")) or
                        section == "WM" or (section == "General" and key == "ColorScheme"))
                       if kind == "kde" else (section == "palettes.ii" if kind == "starship"
                       else section == "Appearance" and key in {"color_scheme_path", "custom_palette"}))
            if allowed:
                changes[(section, key)] = line
    lines = current.splitlines(keepends=True)
    section = ""
    seen_sections = set()
    seen_keys = set()
    for i, line in enumerate(lines):
        match = SECTION_HEADER.match(line)
        if match:
            section = match[1]
            seen_sections.add(section)
        elif "=" in line and not line.lstrip().startswith(("#", ";")):
            key = line.split("=", 1)[0].strip()
            if (section, key) in changes:
                lines[i] = changes[(section, key)] + "\n"
                seen_keys.add((section, key))
    # Insert new keys into their section; never append keys under another group.
    for section, key in list(changes):
        if (section, key) in seen_keys:
            continue
        entry = changes.pop((section, key)) + "\n"
        if section not in seen_sections:
            lines.extend(["\n", f"[{section}]\n", entry])
            seen_sections.add(section)
        else:
            start = next(i for i, line in enumerate(lines)
                         if (match := SECTION_HEADER.match(line)) and match[1] == section)
            end = next((i for i in range(start + 1, len(lines)) if SECTION_HEADER.match(lines[i])), len(lines))
            if end and not lines[end - 1].endswith("\n"):
                lines[end - 1] += "\n"
            lines.insert(end, entry)
    return "".join(lines)


def merge_css(current, generated):
    # Update named color declarations in place, including declarations scoped
    # inside existing light/dark media queries. Keep all selectors and styles.
    definitions = dict(re.findall(r"@define-color\s+([\w-]+)\s+([^;]+);", generated))
    variables = dict(re.findall(r"(--[\w-]+)\s*:\s*([^;{}]+);", generated))
    used_definitions, used_variables = set(), set()

    def definition(match):
        name = match[1]
        if name not in definitions:
            return match[0]
        used_definitions.add(name)
        return f"@define-color {name} {definitions[name]};"

    def variable(match):
        name = match[1]
        if name not in variables:
            return match[0]
        used_variables.add(name)
        return f"{name}: {variables[name]};"

    # Mask comments and quoted strings so examples, imports and content values
    # are never mistaken for active declarations. Keep offsets unchanged.
    mask = re.sub(r'/\*[\s\S]*?\*/|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'',
                  lambda m: re.sub(r"[^\n]", " ", m[0]), current)
    replacements = []
    for pattern, replace in [(r"@define-color\s+([\w-]+)\s+([^;{}]+);", definition),
                             (r"(--[\w-]+)\s*:\s*([^;{}]+);", variable)]:
        for match in re.finditer(pattern, mask):
            # Non-owned declarations retain their original bytes too.
            replacement = replace(match)
            if replacement != match[0]:
                replacements.append((match.start(), match.end(), replacement))
    result = current
    for start, end, replacement in sorted(replacements, reverse=True):
        result = result[:start] + replacement + result[end:]
    missing_definitions = [f"@define-color {k} {v};" for k, v in definitions.items() if k not in used_definitions]
    missing_variables = [f"    {k}: {v};" for k, v in variables.items() if k not in used_variables]
    if missing_definitions or missing_variables:
        result = result.rstrip() + "\n\n"
        result += "\n".join(missing_definitions) + ("\n" if missing_definitions else "")
        if missing_variables:
            result += ":root {\n" + "\n".join(missing_variables) + "\n}\n"
    return result


def main():
    kind, raw_path = sys.argv[1:]
    if kind not in {"css", "kde", "qt", "starship", "chrome"}:
        raise ValueError(f"Unknown theme format: {kind}")
    path = Path(raw_path)
    # Preserve symlinks used by chezmoi/other dotfile managers.
    target = path.resolve() if path.is_symlink() else path
    current = target.read_text() if target.exists() else ""
    generated = sys.stdin.read()
    if kind == "chrome":
        policy = json.loads(current) if current else {}
        colors = json.loads(generated)
        if not isinstance(policy, dict) or not isinstance(colors, dict):
            raise ValueError("Browser policy must be a JSON object")
        color = colors.get("BrowserThemeColor")
        if not isinstance(color, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
            raise ValueError("BrowserThemeColor must be a six-digit hex color")
        policy["BrowserThemeColor"] = color
        result = json.dumps(policy, indent=2) + "\n"
    else:
        result = merge_css(current, generated) if kind == "css" else merge_ini(current, generated, kind)
    if result == current:
        return 1  # Same convention as write_if_changed in apply-gtk-theme.sh.
    target.parent.mkdir(parents=True, exist_ok=True)
    mode = target.stat().st_mode & 0o777 if target.exists() else 0o644
    fd, temp_path = tempfile.mkstemp(prefix=".inir-colors-", dir=target.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(result)
        os.chmod(temp_path, mode)
        os.replace(temp_path, target)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
    return 0


if __name__ == "__main__":
    try:
        status = main()
    except (OSError, ValueError) as error:
        print(f"Cannot merge shared colors: {error}", file=sys.stderr)
        status = 2
    raise SystemExit(status)
