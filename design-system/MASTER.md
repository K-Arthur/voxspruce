# Wayland Voice Control design system

Native GTK4/libadwaita desktop application, using the user-invoked UI/UX Pro Max guidance. Its bundled search script is absent (the `scripts` entry is a text pointer with no target installed); these decisions apply the supplied accessibility rules directly.

- System font and native theme; body 16px-equivalent where practical, headings through native title classes, no downloaded fonts.
- Neutral surfaces, blue primary action, amber review and red stop states, each accompanied by explicit text.
- 8px rhythm; 24px section padding; 12px related-control gaps; generous 44px-or-larger primary controls.
- Views: Voice (record/review/confirm), Commands (searchable exact phrases and risks), Setup (model, mic consent, desktop permission, shortcuts, privacy).
- Native symbolic icons, native keyboard focus and controls, selectable/wrapping help text, no color-only meaning.
- Recording, processing, reviewing, countdown, executing, off and error must be distinct text states.
- Emergency stop remains available in every state. Escape cancels; confirmation never shares the recording gesture.
- Offer both hold-to-talk and explicit start/stop capture so users do not have to sustain a press; both remain consent-gated and duration-limited.
- Announce material status changes to assistive technology without automatically speaking transcript text or repeating countdown ticks.
- Local confirmation explicitly displays destination-selection countdown. Global confirmation acts from the user-selected target.
- Optional practice mode uses its own preview and visibly identifies itself; never imply actual desktop control.
- System light/dark preference and font scaling; no decorative animation. Compact width uses scrolling, never clipped actions.
