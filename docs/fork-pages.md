# CS-Notes fork website

This adaptation builds independently from the checked-out CS-Notes Markdown and images. The Python entry point, design assets and Pages workflow live alongside (not in place of) upstream content. The original notes, images, project license notice and contribution guide are unchanged. Each adapted note opens with a link to its upstream article and original share-alike attribution notice. This is not a GitHub or CyC2018-branded service.

## Build and preview

Install Python 3.10+, Pandoc (official distribution), and Git. On Ubuntu use `sudo apt-get install pandoc`. Run these from a clean checkout:

```bash
bash scripts/build-cs-notes.sh
python3 -m http.server 8769 --bind 127.0.0.1 --directory cs-notes-pages-dist
```

Builds write a new `cs-notes-pages-dist` directory and do not overwrite an existing output. To validate another build, choose a fresh parent via `--out tmp/cs-notes-pages-dist`. Static pages use project-relative links, no external scripts, and no credentials. The search filters visible note titles and categories locally. The site intentionally omits the attack-techniques note from its public rendering without altering the source file.

## Verify

```bash
python3 -m unittest discover -s scripts -p 'test_build_cs_notes.py'
bash -n scripts/build-cs-notes.sh scripts/deploy-cs-notes.sh
```

## Deploy

Repository owner setup: enter **Settings → Pages**, choose **GitHub Actions**, and allow the `github-pages` environment to deploy from `develop`. The new workflow has repository and branch guards and uploads only this project's static output. The inherited upstream website job retains its behavior in the upstream repository, and is skipped in this fork. Keep `master` reserved for upstream sync; it is never a deployment target.

A push to the fork’s `develop` branch builds and deploys. To redeploy that published commit from a clean, matching local `develop` with an authorized GitHub CLI session:

```bash
bash scripts/deploy-cs-notes.sh
```

This dispatches the same workflow. It does not push, change Pages settings or act on `master`. Use the workflow’s deployment URL after the job succeeds.
