# Early testing and launch materials

Prepared 26 October 2026 for a solo maintainer with no paid budget. Drafts are for review; none has been posted. The aim is useful, consented feedback rather than a large announcement. Read each community's rules and participate where a request is welcome. Never claim that automated tests validate real desktop input or assistive usability.

## 1. Invite early Linux testers

**Why:** People can reveal setup and Practice problems before live claims expand. **Effort:** 45–90 minutes to tailor one post and respond; no spend. **Success:** a few specific, privacy-conscious reports—not a target number or promise.

First: select one relevant Linux or Wayland community that permits project posts; run the Practice quick start on a clean setup; post the following with its local rules respected.

> I'm working on Voxspruce, an experimental Linux app exploring accessible and private voice input. It starts in a typed Practice mode, and its live recognition uses a local model with explicit review before input. Real GNOME Wayland input, microphone workflows, and assistive-technology use still need validation; please don't rely on it for essential tasks. If you have time, I'd appreciate a Practice test or a carefully documented live test using a disposable destination: https://github.com/K-Arthur/voxspruce . Please don't share recordings, transcripts, or private information.

## 2. Invite contributors to the validation matrix

**Why:** The main bottleneck is real-session evidence, not a larger feature list. **Effort:** 30–60 minutes to identify one open task and write an invitation; ongoing review as available. **Success:** a reproducible finding, an improved checklist, or a focused contribution.

First: review [release readiness](../release-readiness.md) and [manual tests](../manual-test.md); identify a specific unvalidated workflow and an appropriate contributor venue; invite help without implying the work is already supported.

> Help wanted: Voxspruce needs careful validation of real GNOME Wayland permissions and input, microphone handling, and accessibility workflows. Practice and automated checks exist, but they do not establish real-world support. Pick a task in the test guide, use disposable examples, and share a sanitized result or improvement: https://github.com/K-Arthur/voxspruce/blob/main/CONTRIBUTING.md . Partial or unsuccessful results are useful too.

## 3. Publish an educational explainer when ready

**Why:** A useful explanation can answer actual questions and earn trust without overstating the product. **Effort:** 2–3 hours to review and adapt; free. **Success:** useful discussion and a small number of informed testers or document improvements.

First: verify the current privacy and compatibility docs; write a brief explanation in a venue that permits it; respond to questions and correct errors. Do not make competitor claims without fresh primary-source evidence.

> **What does offline voice input on Linux require?** Local recognition processes speech on your machine after you install a recognizer and model; downloading them is a separate network step, and the model has its own license. A desktop app may also need microphone access and permission to send input. Voxspruce experiments with local recognition and a review-before-confirm workflow. Its live desktop and accessibility behavior still need real-world testing. See its [privacy model](https://github.com/K-Arthur/voxspruce/blob/main/docs/privacy.md) and [compatibility limits](https://github.com/K-Arthur/voxspruce/blob/main/docs/compatibility.md).

## Lightweight measurement

Once a month, record date, source, and observations in a maintainer-owned note: GitHub traffic and referrers when available; number of useful Practice/live reports; actionable contributions; and which validation gaps gained evidence. GitHub traffic is aggregated, incomplete, and time-limited; stars are not successful user outcomes. No application telemetry is needed.

Repeat a small query set in an ordinary browser and available AI search tools: “offline voice input Linux Wayland”, “accessible voice control Linux”, “private dictation GNOME Wayland”, “Voxspruce privacy”, and “Voxspruce compatibility”. Record date, region, platform, whether the project is found/cited, and whether descriptions are accurate. Results vary by personalization and change over time; absence or citation alone does not prove performance. Improve the underlying documentation when factual gaps surface.
