# Real-session validation and the kill test

This checklist is a release gate, not a claim that the tests have been performed. Automated adapters and Xvfb GUI tests cannot establish actual compositor input behavior or speech usability.

## Record the test environment

Record date, distribution/version, GNOME Shell version, Wayland session, xdg-desktop-portal and GNOME portal backend versions, PipeWire version, keyboard layout, model name/license, microphone, CPU, and application versions. Use a disposable text editor and a disposable unsent form. Do not begin in a terminal, password field, real message or production document.

## Week-one input decision

1. Start the application in default Practice with microphone consent disabled. It must neither construct live adapters nor record or present a permission dialog. Exercise a typed practice example and inspect simulated output. Switch to Live; select/save and explicitly prepare an extracted model. Enable mic consent only when ready for an explicit capture.
2. In Live Setup, request keyboard access. Deny it. Confirm that all input remains blocked and retry is available.
3. Request again. Grant keyboard access in the desktop dialog. Check that no screen-sharing source was requested and the app accurately reports granted permission.
4. In Live Dictation mode, hold to speak `Wayland voice test 123.`, release, review the final transcript and confirm it. Select the editor during the visible countdown. Record exact output, duplication, missing characters, latency and whether any unexpected key is pressed.
5. Repeat with punctuation and the languages/layouts being claimed. Record characters that fail. Do not generalize from ASCII success to Unicode support.
6. Test next/previous field, copy/paste, select all and undo in disposable text. Test press Enter, close window and delete selection only in disposable contexts, after both confirmations. A single confirmation must never execute those actions.
7. Revoke permission using the desktop controls while an action is pending and again during a countdown. There must be no later injection. Reconnect must not replay the old action.
8. Press emergency stop during capture, review, countdown and a long insertion. Verify the microphone closes, pending work is discarded and keyboard permission ends. A partial insertion must be reported honestly; do not retry automatically.
9. Verify modifier keys are not left pressed after success, cancellation, denial or an input failure. Check the physical keyboard still behaves normally.
10. Quit/restart. No recording, transcript, pending action or permission token should return.

**Pass:** The supported permission path works repeatedly and predictably on the recorded GNOME session without privileged input helpers. **Fail/rescope:** It cannot deliver reliable input through supported APIs. Keep practice/review usable, but do not advertise desktop-control support or replace the portal with a bypass.

## Push-to-talk and local recognition

- With mic consent off, mouse, keyboard and global shortcuts must not open capture.
- Press/hold and release; inspect actual PipeWire capture lifetime. Test very short holds, rapid repeats, lost focus, lost pointer grab, Escape, permission revoke and application quit.
- Start another permitted capture/voice app at the same time. PipeWire may route the microphone to both; verify the stream is identified as Wayland Voice Control, this app warns that capture is shared, and stopping it leaves the other app's stream active. Pause the other voice app when checking recognition to avoid competing listeners.
- Request global shortcut bindings when a requested chord is already claimed by the desktop or another app. Confirm the desktop chooser controls conflict resolution, only returned bindings are shown as bound, and every missing binding is clearly marked with a local-control fallback.
- If another voice-control app can inject keyboard input, keep it active only in a disposable field and verify its concurrent input can interleave. Confirm that Setup advises pausing it before this app's reviewed input; the portal cannot arbitrate which app should type into the focused field.
- While model preparation is idle/loading/error, neither local nor global hold may start capture. Prepare explicitly, then test release during microphone startup: capture must not start afterward. During processing, stop: a late transcript must not revive the session.
- Hold past the configured duration cap; capture must stop, the recording indicator must clear, auto-repeat must not restart it, and a physical release followed by a new hold must work. Repeat after moving focus to another widget and another top-level window before release; refocusing the app must allow a new genuine press. If the recorder exits early or the microphone disappears, show a recoverable error.
- Test the explicit start/stop control with mouse and keyboard/screen reader. It must start only after consent, cancel safely during startup, stop on a second activation, and stop at the same duration cap. Check that status announcements describe state changes without speaking the transcript automatically.
- While using the explicit start/stop control, switch to another window during capture. Capture must cancel and the status must report the stopped state. This local-focus safety rule does not apply to an explicitly requested desktop global push-to-talk binding.
- Disconnect the network after local dependency/model setup. Dictation and commands must work without outbound connections. No temporary audio files or transcript logs should appear.
- Compare recognized text to intended speech using at least two accents and two microphones. Record failures, not only successful takes. Do not publish an accuracy percentage without a defined sample and scoring method.

## Shortcut and focus behavior

- Decline shortcut binding and verify local controls still work.
- Approve shortcut binding and display the actual assigned trigger. Test hold-to-talk press/release outside the app.
- Review a transcript, focus the disposable destination and invoke confirm. Verify shortcut modifier keys do not change the injected text.
- Hold or auto-repeat confirm: one physical confirmation event must not satisfy both stages of a risky action.
- Change focus during countdown. The app cannot identify semantic target fields; the displayed instructions must make this limitation clear.

## Accessibility and portfolio evidence

Follow the complete [accessibility release matrix](accessibility.md). Test full navigation with keyboard only and with Orca, including setup, denial/retry, transcript editing, both capture controls, the two confirmation stages and emergency stop. Browse by headings and groups; confirm control names, checked/disabled states, visible focus, useful status announcements and that private transcript content is not announced without request. Test Orca speech and braille, high-contrast theme, system text scaling at 200% and 400%, light/dark themes, a compact window and reduced motion. Test switch scanning and ask disabled voice-input users whether hold-to-talk or start/stop capture works with their input devices. Record completed tasks, failure recovery, versions and consented feedback; do not infer support for other disabilities from one participant or one screen reader.

Capture a captioned demo with dictation, two commands, one recognition error, cancellation, and permission revocation. Obtain participant consent before recording. Store neither participant audio nor private transcripts in the repository. Publish the exact tested matrix and unresolved limits alongside the demo.


## Custom shortcut and edit regression checklist

Use disposable destinations and explicit permission; this checklist is not a
record of hardware verification. Configure `save document` → `Ctrl+S` with a clear
description. Check exact matching, normalized case/spaces, disabled state,
built-in/duplicate collisions, invalid/multiple chords and field length errors.
Practice must display the phrase, exact chord, description, high risk and simulated
result without microphone/portal access. Both confirmations remain necessary.

During live held recognition, final review, second confirmation and focus
countdown, edit/disable/delete a custom shortcut. Check microphone/draft cleanup,
cancelled approval/timer, ignored late callbacks and global confirm doing nothing.
A bound action already handed to input must release attempted keys, never change
its chord or retry. Test modifier cleanup after cancellation and injected failures
in the isolated portal tests before real-session checks.

Arm dictation, enter editing, select all, delete, and retype. Global confirm during
the empty or newly typed buffer must send nothing. Invalid controls must remain
correctable. Explicit re-review creates a fresh ID/expiry and requires confirmation
again. Repeat from second confirmation; cancel an edit and attempt a stale edit
signal during newer work. Check expiry before editing and stale countdown callbacks.

Back up an intentional v1 configuration, open it in the new app and verify every
preference survives the atomic v2 migration. Restart with enabled/disabled custom
shortcuts, edit/delete them, and verify reset removes them while restoring defaults
and microphone consent off. Never put recordings or private speech in fixtures.
