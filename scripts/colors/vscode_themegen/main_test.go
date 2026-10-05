package main

import (
	"os"
	"path/filepath"
	"testing"
)

func TestPaletteRefreshPreservesEditorSettings(t *testing.T) {
	home := t.TempDir()
	t.Setenv("HOME", home)
	t.Setenv("XDG_CONFIG_HOME", filepath.Join(home, "config"))
	t.Setenv("INIR_INSTALL_SHARED_APP_CONFIGS", "false")
	settingsPath := getSettingsPath("Code")
	if err := os.MkdirAll(filepath.Dir(settingsPath), 0o755); err != nil {
		t.Fatal(err)
	}
	settings := []byte(`{
// Keep my editor configuration and selected theme.
"editor.fontFamily": "Personal Font",
"workbench.colorTheme": "Personal",
"workbench.colorCustomizations": {"foreground": "#123456"}
}`)
	if err := os.WriteFile(settingsPath, settings, 0o600); err != nil {
		t.Fatal(err)
	}
	colorsPath := filepath.Join(home, "colors.json")
	if err := os.WriteFile(colorsPath, []byte(`{"background":"#112233","primary":"#aabbcc","on_surface":"#eeeeff"}`), 0o600); err != nil {
		t.Fatal(err)
	}
	extDir := filepath.Join(getExtensionsDir("code"), themeExtensionID)
	if err := os.MkdirAll(extDir, 0o755); err != nil {
		t.Fatal(err)
	}
	registry := filepath.Join(getExtensionsDir("code"), "extensions.json")
	invalid := []byte("{invalid registry}")
	if err := os.WriteFile(registry, invalid, 0o600); err != nil {
		t.Fatal(err)
	}
	for i := 0; i < 2; i++ {
		if ok, err := generateThemeForFork(colorsPath, "", "", settingsPath, "code"); !ok || err != nil {
			t.Fatalf("generation failed: %v", err)
		}
	}
	for path, expected := range map[string]string{settingsPath: string(settings), registry: string(invalid)} {
		actual, err := os.ReadFile(path)
		if err != nil || string(actual) != expected {
			t.Fatalf("modified personal file %s: %v", path, err)
		}
	}
	if _, err := os.Stat(filepath.Join(extDir, "themes", themeFileName)); err != nil {
		t.Fatal("missing generated theme", err)
	}
	if !stripThemeForFork(settingsPath, "code") {
		t.Fatal("strip failed")
	}
	actual, err := os.ReadFile(settingsPath)
	if err != nil || string(actual) != string(settings) {
		t.Fatal("strip changed personal settings", err)
	}
}
