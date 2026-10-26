# Naming exploration

Checked 26 October 2026. **Voxspruce was selected for the public-facing name.** The repository is renamed to `K-Arthur/voxspruce`; package, command, desktop, D-Bus, and application identifiers retain their earlier names for compatibility. Subtitles describe intended use, not validated support.

| Candidate and proposed subtitle | Strength | Tradeoff and preliminary conflict checks |
| --- | --- | --- |
| **Voxspruce — Experimental voice input for Linux** | Distinctive and easy to pair with a descriptive subtitle; recommended for further investigation. | “Vox” may need explanation; the tree metaphor does not explain accessibility. Exact-name web search returned no clear product match in this limited check. GitHub repository-name search returned zero matches and the exact PyPI project endpoint returned 404. |
| **Voxfern — Experimental voice input for Linux** | Short and pronounceable with a gentle tone. | Existing [VoxFern username](https://archidekt.com/search/decks?name=&orderBy=-updatedAt&ownerUsername=voxfern&page=1) and social uses create potential confusion. GitHub repository-name search returned zero matches and the exact PyPI project endpoint returned 404. |
| **Voxgrove — Experimental voice input for Linux** | Suggests a community and can accommodate future scope. | [VoxGrove School Prep](https://obscurevox.bond/) uses the name elsewhere. GitHub repository-name search returned zero matches and the exact PyPI project endpoint returned 404. |

The checks are point-in-time, exact-name screening, not a trademark, domain, pronunciation, accessibility, global-language, or legal clearance. Search engines may miss uses, GitHub search is not a username/organization check, and a PyPI 404 is not a reservation. Before expanding the brand or changing technical identifiers, repeat checks for organizations, domains, package registries and relevant marks; ask intended users about comprehension and pronunciation. A separate migration plan would be needed for package ownership, desktop IDs, D-Bus activation, app data, and compatibility.

GitHub currently redirects the old repository URL and Git remote to the new one. Do not reuse the old repository name: that would stop the redirect. GitHub does not redirect references to actions hosted in a renamed repository; there is no published action in this project. See [GitHub's rename guidance](https://docs.github.com/en/repositories/creating-and-managing-repositories/renaming-a-repository).
