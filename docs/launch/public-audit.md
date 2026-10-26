# Public repository audit

Initial audit: 26 October 2026. The repository was already public. This is a limited review, not a comprehensive security, privacy, legal, or license audit.

- The reachable Git history was scanned across 541 path-bearing objects for common GitHub token, AWS access key, private-key block, and quoted credential-assignment patterns. No matches were found. Pattern scans miss other secrets and cannot establish that history is clean.
- Commit author metadata includes the maintainer's public name and GitHub noreply address, and Dependabot's public noreply identity. Review whether the public author name is intended; no history was rewritten. Ignored local models, environments, databases, build artifacts and worktrees are not tracked at the audited commit; ignored files can still exist locally.
- The project has an MIT license. The optional Vosk package, distribution dependencies, upstream test fixtures and separately downloaded speech models have their own licenses and distribution terms. No downloaded models or public WAV fixtures were found among tracked files. Verify third-party terms for each model or redistributed artifact; this review is not legal clearance.
- The package and docs reference the Vosk model catalogue, PyGObject instructions, portal specifications and project GitHub pages. Automated link checking should be repeated at release; remote sites and GitHub route availability can change. The GitHub security reporting route requires private reporting to remain enabled.
- GitHub secret scanning and push protection were already enabled. Private vulnerability reporting, Dependabot alerts, and security updates were enabled during this work. Dependabot version-update configuration already exists. These mechanisms do not guarantee detection or automatic remediation of all vulnerabilities.
- There was no published release, and real-session release gates remain open. No public release, announcement, or history rewrite is part of this work.
