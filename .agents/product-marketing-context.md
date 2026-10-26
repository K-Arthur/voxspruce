# Product marketing context

Last reviewed: 2026-10-26. This is a working document; assumptions and unanswered questions are not evidence of user demand.

## Product

**Current name:** Voxspruce (formerly Wayland Voice Control). **Category:** experimental offline voice input and desktop commands for Linux/Wayland. **Model:** free, MIT-licensed community software; speech models have separate licenses. No paid offering or account is documented.

The GTK4/libadwaita application provides typed Practice, locally recognized dictation, and exact commands. Users review and explicitly confirm an action; high-risk and custom commands need a second confirmation. Live use needs a separately acquired local Vosk model, explicit microphone consent and desktop-granted keyboard permission. Normal recognition and review run locally without a cloud recognition fallback or telemetry. Installation and obtaining models use the network. [README](../README.md) · [privacy](../docs/privacy.md)

## Audience and jobs

**Purpose:** explore more accessible voice input while respecting privacy and user control. People with accessibility needs are central to the purpose; do not assume their needs, abilities, assistive technologies or preferences are uniform. Early testers and contributors comfortable with Linux can help validate the workflow. An unsupported assumption is that this audience wants the current review flow; validate with voluntary, consented feedback.

**Jobs to investigate:** enter text by voice; carry out a small set of desktop actions after review; understand and control when capture and input happen. For early testers, an additional job is to reproduce and share results without disclosing private speech.

**Not yet a good fit:** anyone who needs a proven, always-listening, hands-free, certified assistive product or dependable live input today. Built-in commands are English; recognition depends on the selected model. See [compatibility](../docs/compatibility.md).

## Problems, alternatives, and differentiation

Hypotheses to validate: users may encounter friction from keyboard input, unclear permission boundaries, or the need to send speech to a remote service. We do not yet know their prevalence, costs, actual words, or which alternatives users prefer.

Offline privacy is not unique: nerd-dictation and Myna also support local recognition. Talon, nerd-dictation, and Myna have different scopes and platform choices. The proposed distinction is the combination of a native review/confirmation workflow, Practice mode, and desktop portal consent—not proven superiority. Evidence and caveats: [research](../docs/research.md).

## Switching dynamics and objections

- **Push / pull, hypotheses:** keyboard or current voice workflow may be difficult; explicit review and local recognition may be attractive.
- **Habit / anxiety, hypotheses:** existing tools may already work; experimental status, installation, accuracy, permissions, and unexpected desktop input can deter trying this project.
- **Response:** lead with Practice and clear limits, explain local-model setup and permissions, use disposable destinations, and report partial failures without automatically retrying. Do not promise safety, reliability, or accessibility conformance.

## Voice and proof

Tone: direct, respectful, technically clear, welcoming, and candid. Say “designed with accessibility and privacy in mind,” “experimental,” “local recognition,” and “review and confirm.” Avoid claiming certified accessibility, universal hands-free operation, guaranteed privacy, supported desktops or languages without evidence, or superior accuracy.

Evidence: isolated automated controller, GTK, accessibility-transport, and portal protocol checks; a local model/fixture benchmark on a specified host. These do not prove real microphone, compositor, screen reader or intended-user outcomes. [Validation](../docs/validation.md) · [release gates](../docs/release-readiness.md). No verified user quotes, testimonials, adoption metrics, or customer language are available yet; do not invent them.

## Goals and measurement

Primary near-term goal: find early testers and contributors who can help validate real workflows. Desired action: try Practice, then submit a useful privacy-conscious report; live testing is optional and subject to the documented limits. Record useful reports, contribution activity, repository traffic when available, and a small repeatable search/AI-query check. No baseline or targets are known. See [launch plan](../docs/launch/marketing.md).
