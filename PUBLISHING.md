# Publishing Coating Lab

The MCP Registry accepts the listing only after the PyPI package is live, and checks that the README on PyPI carries
`mcp-name: io.github.hpdkhoa/coatinglab-mcp` (README.md holds it as an HTML comment).

1. **GitHub:** push `main` to https://github.com/hpdkhoa/coatinglab-mcp and tag the release (`git tag v0.1.0`,
   `git push --tags`).
2. **PyPI**, with your token from your password manager (never in a file):

       python -m pip install build twine
       python -m build
       python -m twine check dist/*
       python -m twine upload dist/*

3. **The MCP Registry**, in this folder: `mcp-publisher login github`, then `mcp-publisher publish`.

Each release: `python -m pytest tests` (set COATINGLAB_TEST_BUILD to a Model Lab build for the bake test), raise the
version in `pyproject.toml`, `src/coatinglab/__init__.py` and `server.json` (both fields), add it to CHANGELOG.md.
