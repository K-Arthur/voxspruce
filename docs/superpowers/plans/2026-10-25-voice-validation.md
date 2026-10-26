# Voice lifecycle and accessibility validation follow-up

Goal: close concrete lifecycle faults found during the full-system audit, and
validate the native accessibility transport without user speech or host input.
Scope continues the approved permission/cancellation, shortcut-conflict and
accessibility requirements. Human speech, real compositor insertion and Orca
usability remain distinct release gates.

1. Test first and fix portal service owner loss/replacement. A vanished owner
   invalidates pending requests, keyboard grants and shortcut sessions, cancels
   capture/review/countdown, and cannot reconnect/replay automatically. Old owner
   callbacks must not restore grants. Verify the actual Gio wire on a private bus.
2. Test first and handle GlobalShortcuts.ShortcutsChanged for this session.
   The payload describes changed shortcuts, so preserve omitted bindings; refresh
   displayed assignments and cancel held/pending work safely without synthesizing
   a confirm release. Ignore stale sessions and close subscriptions correctly.
3. Add a reproducible isolated AT-SPI integration check that navigates the actual
   native app and exercises Practice editing/review/cancel and custom-command
   configuration using accessibility interfaces. No GTK test backend, host input,
   microphone, real keyboard grants or transcript output. Use temporary settings,
   private session/accessibility buses and bounded cleanup. Run on the local host
   and CI where distribution AT-SPI libraries are available.
4. Obtain specification review followed by quality review. Run relevant/full
   native tests, protocol checks, static checks and build; update documentation
   with exact evidence and unverified claims. Commit progressively, merge main
   and push as authorized.
