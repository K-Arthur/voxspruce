# Accessibility target and verification

Voxspruce is a Linux desktop app, not a screen reader. Google's
TalkBack is Android's built-in screen reader; it cannot be a direct comparator
for a GTK application. The Linux target is a clear, dependable experience through
GTK's AT-SPI accessibility tree, Orca speech and braille, keyboard navigation,
system magnification/contrast, switch scanning, and the app's own offline speech
controls. GTK exposes roles, names, relations and states to AT-SPI; user testing
with Orca remains necessary to know how those attributes are actually presented.

The current implementation provides native GTK controls, explicit accessible
names for inputs and actions, named semantic groups, navigable headings, a status
announcement that excludes transcript text, keyboard operation, enlarged capture
controls, wrapping/scrolling, system appearance and an optional local transcript
read-back. Recording can be held or started/stopped with separate activations.
There is no always-listening wake word. For speech output, read-back is an
explicit user action and Stop cancels it.

## Release evidence required

| Area | Automated checks | Manual evidence still required |
| --- | --- | --- |
| Orca speech and braille | GTK accessibility test backend checks roles, labels, group/heading hierarchy, status role and transcript-free announcement payloads; the private AT-SPI check exercises named controls and the Practice review/edit/custom-shortcut workflow through the actual accessibility wire | In an actual GNOME Wayland session, browse all three views by headings, landmarks/groups and controls; complete setup, edit/re-review, custom shortcut configuration, cancellation and stop. Repeat with speech and refreshable braille if available. Record Orca/GTK versions and issues. |
| Keyboard and switch access | Native widget tests verify actionable roles; XTest drives the start/stop control through real Space key events under Xvfb | Complete every task with keyboard only, then with switch-scanning assistive software available on the tested distribution. Confirm visible focus, logical order, no trap, no timing-dependent activation and emergency stop reachability. |
| Low vision and color | Compact/default screenshot review; native system theme and text scaling; labels and status text supplement color | Test system text scaling at 200% and 400%, high-contrast theme, light/dark, compact windows and focus visibility on GNOME and KDE. Check focus/disabled/error states and confirm no clipping or color-only information. |
| Motor access | Both hold and click-to-start/stop paths are automated; local toggle capture cancels on focus loss and on pending-start cancellation | With disabled users, assess the reachability/effort of starting, stopping, editing and confirming. Try keyboard, switch access, dwell/alternate pointer, and user-configured global push-to-talk. Confirm the duration cap and focus behavior do not prevent task completion. |
| Speech and language | Offline Vosk decode/throughput benchmark, capture lifecycle tests, bounded drafts and review-before-action policy | Collect consented, privacy-preserving task outcomes across supported local models, microphones, accents, speech disabilities and quiet/noisy environments. Measure word error rate, correction effort, completion rate and end-to-end latency. Never infer this from a public fixture. |
| Understanding and error recovery | Exact command matching, explicit risk/confirmation states, cancellation, expiry and sanitization tests | Ask participants with cognitive, learning, hearing and vision disabilities to complete realistic tasks. Verify setup and error messages, custom phrase discoverability, draft/final distinction, confirmation countdown, recovery and privacy are understandable. |

Each manual run should record task success, time, errors, recovery, assistive
technology versions and participant-approved feedback. Obtain informed consent;
do not commit recordings, identifiable notes or private transcripts. Include more
than one person and more than one disability/access method; one successful Orca
smoke test is not evidence for all disabled users.

## Claim boundary

Automated GTK accessibility tests establish that the app describes selected
widgets through GTK's test backend. The separate isolated AT-SPI integration
check verifies actual transport and selected accessible Practice actions using
synthetic text. Neither establishes Orca output, braille quality, switch scanning,
speech accuracy for a person, or usability. The local environment has no Orca
executable. The check uses its own registry rather than the user's desktop
registry; the manual Orca and intended-user matrix remains open.

Do not claim that the app is "better than TalkBack" or "optimized for disabled
people" from the current evidence. A defensible future statement should list the
specific tested combinations and the tasks participants completed, for example
"tested with Orca X on GNOME Y for setup, dictation review and custom shortcuts",
and include known limitations. A product-level comparative claim needs a
pre-registered, like-for-like study with TalkBack users and a defined task set.

References: [GTK accessibility](https://docs.gtk.org/gtk4/section-accessibility.html),
[Orca and AT-SPI](https://gnome.pages.gitlab.gnome.org/orca/help/introduction.html),
[Android accessibility testing and TalkBack](https://developer.android.com/guide/topics/ui/accessibility/testing),
[WCAG focus visible](https://www.w3.org/WAI/WCAG22/Understanding/focus-visible),
and [WCAG target size](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum).
WCAG is used here as a useful interaction reference; this document does not claim
conformance for a native desktop product.

## Background controls and optional Plasma widget

A session-only background option and explicit Quit keep lifecycle choices
visible. The widget uses native button semantics, keyboard operation, accessible
names, wrapping labels and a scrollable expanded layout. Recording status is
textual as well as graphical; no transcript is sent to shell UI. Its recording
control supports separate start/finish activations, and Cancel/Stop remain
available. Review/confirmation remains in the main app. These mechanisms still
require Orca and intended-user testing on the actual desktop; widget test passes
are not a broad disability-optimization or TalkBack parity claim.
