# Contributing and testing

Thank you for helping improve accessible, private voice input on Linux. This is experimental software; please use disposable text and destinations and do not rely on it for essential tasks. Practice is the safest starting point and does not open a microphone or portal.

## Help test

1. Follow the [Practice quick start](README.md#quick-start-practice-mode), then try entering, editing, reviewing, and confirming a simulated action.
2. If you choose to test live input, read the [manual test guide](docs/manual-test.md), [privacy model](docs/privacy.md), and [compatibility limits](docs/compatibility.md) first. Live input needs a separately obtained Vosk model, explicit microphone consent and an actual desktop keyboard grant. A failed insertion can leave partial text.
3. Share what worked or failed using the [test report form](https://github.com/K-Arthur/voxspruce/issues/new?template=test-report.yml). Note your distribution, versions, session and desktop, whether the test was Practice or Live, and whether any portal grant was actually made. A report that a test could not be completed is useful too.

Please do not include recordings, transcripts, private paths, device identifiers, tokens, or information about another person. Check screenshots and logs before posting. Participation is voluntary; do not disclose a disability or diagnosis. For suspected security issues use [private reporting](SECURITY.md).

## Help build

Look through [open issues](https://github.com/K-Arthur/voxspruce/issues), or open one describing the change before investing in a large proposal. Fork the repository, create a branch, and submit a pull request describing the change and the checks you ran. Small documentation and accessibility improvements are welcome.

Use the setup and test commands in [development and distribution](docs/development.md). Backend tests run without a display; native and portal checks need the listed dependencies and isolated test sessions. Follow the [manual test guide](docs/manual-test.md) for real compositor tests. Automated or simulated results should not be presented as real desktop, screen-reader, or intended-user validation.

By participating, follow the [code of conduct](CODE_OF_CONDUCT.md). Contributions are submitted under the project's [MIT license](LICENSE); verify that any third-party material can be redistributed and attributed appropriately. Separate speech models have their own licenses.
