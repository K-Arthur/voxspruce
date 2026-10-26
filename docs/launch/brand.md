# Voxspruce brand guide

Voxspruce is the public-facing name of this experimental Linux voice-input project, previously called Wayland Voice Control. Keep the repository URL, package name, command, application IDs, and configuration paths unchanged for compatibility. The voice is direct, respectful, welcoming, technically clear, and candid about limitations.

## Mark

The mark combines a spruce silhouette, a voice waveform and a V-shaped base. Use the [full-color SVG](assets/voxspruce-mark.svg) on light backgrounds, the [light-on-dark SVG](assets/voxspruce-mark-dark.svg) on dark backgrounds, or the [dark monochrome](assets/voxspruce-mark-mono.svg) and [light monochrome](assets/voxspruce-mark-mono-light.svg) marks for single-color uses. The app icon places the mark on a pale rounded surface for contrast in desktop environments.

Preserve proportions and leave at least one waveform-bar width of clear space. Prefer the app icon for small launchers; at tiny sizes, test the actual rendered result and do not rely on color alone to communicate function. Do not recolor individual elements arbitrarily, distort the mark, or place the dark version directly on dark surfaces.

## Palette and typography

- Deep evergreen `#103E39`: primary mark on light surfaces and dark backgrounds.
- Teal `#0B7166`: complementary mark on light surfaces.
- Pale mint `#E9F7F1`: app-icon surface.
- Light mint `#79E3C4` and off-white `#E7FFF5`: mark on dark surfaces.

Use system sans-serif type and native GTK typography inside the application. Treat accent and status colors according to the [design system](../../design-system/MASTER.md); branding does not replace accessible semantic colors or text labels. Check contrast in each context rather than assuming every palette combination is suitable for small text.

## Social preview

[Social preview](assets/social-preview.png) uses a dark background and a bright interpretation of the mark. Keep the experimental and Linux context visible when adapting it. The exact rendered text is “Voxspruce”, “Voice input for Linux”, and “EXPERIMENTAL · LOCAL-FIRST · OPEN SOURCE”. GitHub may crop previews differently across services, so inspect after upload. The preview is rendered from the same canonical mark as the desktop icon. Run `python3 scripts/build-brand-assets.py` and `python3 scripts/build-social-preview.py` after editing the mark; the latter requires `rsvg-convert`. The logo concept was developed using OpenAI built-in image generation and redrawn as SVG for clean, scalable reuse.
