# Research and decisions

Checked 25 October 2026. Purpose: choose the scope and integration path for a free community tool, not estimate a commercial market. No reliable audience size is asserted.

## Product evidence

| Alternative | Verified product evidence | Implication for this project |
| --- | --- | --- |
| Talon Voice | The official changelog says Talon 1.0 is planned as the last public Linux/X11 release, while Talon+ retains Linux/X11 support. It also describes Wayland detection/warnings. | Do not claim Talon has ended all Linux support. Test a narrow permission-based Wayland workflow rather than attempting full Talon parity. |
| nerd-dictation | Its upstream README describes Vosk-based offline dictation and selectable xdotool, ydotool, dotool and wtype input utilities. | Offline dictation is already available. The distinction here is a native review flow and a standard desktop consent boundary, whose reliability still needs testing. |
| Myna | Canonical's 12 October 2026 announcement describes local dictation, no audio upload/storage, and GNOME Wayland on specified Ubuntu releases. It explicitly says the preview does not control the desktop using voice commands. | Privacy alone is not differentiation. A small confirmed command set is a plausible gap, not proof of user demand. |

Sources: [Talon official changelog](https://talonvoice.com/dl/latest/changelog.html), [nerd-dictation upstream](https://github.com/ideasman42/nerd-dictation), [Canonical Myna preview announcement](https://ubuntu.com/blog/myna-speech-to-text-technology-preview-available), [Myna upstream](https://github.com/canonical/myna).

The [Kubuntu 26.10 release note](https://discourse.ubuntu.com/t/kubuntu-26-10-is-out-whats-actually-on-the-iso/89576) supports the brief's Wayland transition context. It does not validate this application's GNOME or KDE behavior.

## Requested Vibe Prospecting research

The competitor-research workflow was attempted for the three named alternatives. Only Canonical resolved as a company; Talon Voice and nerd-dictation did not. Firmographics, funding and workforce enrichment and a 90-day event query were completed, and both final samples were revealed. No export was requested or performed.

Canonical's company-wide data cannot estimate Myna's team, budget or support commitment. Funding and company-status fields were empty. Workforce data was dated 1 July 2026 and change-field units were unclear, so no hiring/layoff inference is made. The event sample included a Myna announcement, but its date was truncated; the date above comes from Canonical's primary announcement. SEC-derived strategy, challenges, technographics and review ratings were not used. There is insufficient comparable company data for a credible size/funding battlecard of these community projects.

Hypotheses: unique offline/private dictation is contradicted; a confirmed command workflow is a plausible product distinction; demand from real voice-input users remains untested. Customer overlap is partial for Myna's desktop dictation use case; unresolved from company data for the other two projects.

Interview prompts before expanding the catalogue: Which five actions are essential? Can the user comfortably hold a switch or shortcut? How should they review/cancel a misrecognized command? Which apps and keyboard layouts must work? What happens if focus changes during confirmation?

## Technical sources and decisions

- [RemoteDesktop portal](https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.RemoteDesktop.html): request a keyboard-only session and check granted devices. Use the documented D-Bus Notify input path. EIS is recommended upstream but is a separate alternative; this version does not open EIS. No permission persistence tokens are retained.
- [GlobalShortcuts portal](https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.GlobalShortcuts.html): desktop-approved shortcut sessions provide activation and release signals. This avoids device-level key monitoring. Actual availability and granted triggers must be displayed.
- [Vosk installation](https://alphacephei.com/vosk/install) and [model catalogue](https://alphacephei.com/vosk/models): a local small English model is the initial candidate. Model quality and recognition latency must be measured with intended users, not inferred from benchmark numbers.
- PipeWire `pw-record --help` on the development host confirms raw mono signed-16-bit output to stdout; runtime does not create an audio file.

## Validation status

The development host reports CachyOS, KDE and Wayland; GTK4/libadwaita are installed. Read-only D-Bus introspection confirms RemoteDesktop (keyboard advertised) and GlobalShortcuts exist. No consent dialog was auto-accepted and no desktop input was injected during that inspection. This is capability discovery, not an end-to-end input test. GNOME, actual microphone/model accuracy, other layouts, and testing with voice-input users remain release gates in the manual validation checklist.
