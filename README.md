# Anonymous submission website

Supplementary website for **Coding Agents for Generalized Task and Motion Planning Problems**.

- Website: https://r8508271-lang.github.io/
- Anonymous research code: https://anonymous.4open.science/r/agentamp-3481/
- Manuscript: `assets/paper.pdf`, the submitted ICRA 2027 manuscript 4501, preserved unchanged.

## Contents

The page includes the experimental setup, a gallery, the submission video, results from Tables I–III, and a browser for all 28 environments. The six result rows correspond to five program-synthesis methods and a planning baseline. There are 700 synthesized programs and 70,000 evaluation episodes. Table III compares 44 matched seeds across 13 environments: 4.002 ms/action in the main setting and 27.900 ms/action with source access.

`data/benchmark.json` is the canonical numeric table; `data/benchmark.csv` is its downloadable equivalent. Means, min/max ranges, and missing planner entries were checked against the submitted PDF. The source-access reference is separate from the main setting. Missing results are not counted as failures.

`data/policy-examples.json` contains 84 verified clips across 28 environments, with three methods per environment. Each environment uses the same held-out instance across methods. Captions show replay outcomes and action counts; selected clips are not representative averages. Backgrounds are enabled in dynamic 3D scenes. Clip provenance records program, evaluation, initial-state/frame, and media checksums. All policy comparisons are complete. ScoopPour uses episode 0 with 10 objects, the first episode with matching object counts across the three archived evaluations; all three policies were rerendered on that shared instance.

The exact environment descriptions supplied to the agent are in `data/environment-descriptions/`. Their checksums are recorded in `sources.json`; `data/environment-descriptions.json` contains the rendered descriptions. Videos are examples for readers, not agent inputs. Selecting an environment starts its available videos together. The panel order is videos, method results, then the agent's input text.

The gallery uses four columns on desktop, two on tablets, and one on small screens. Videos play at 8× by default, with 1×, 2×, 4×, and 8× controls. Videos pause off screen or when the tab is hidden; reduced-motion and data-saving preferences disable automatic gallery playback.

The main video is the provided submission MP4, with its original audio and a title-frame poster. `film/assets/` contains only the gallery clips and licensed fonts required by this page. The Inter font license is retained in `film/assets/fonts/OFL.txt`.

## Local preview and checks

```sh
npm start
npm run check
npm test
```

Open http://127.0.0.1:8770/. The local server supports seeking in videos. To regenerate the CSV after changing the canonical table, run `python3 scripts/export_csv.py`.

## Anonymous publication

```sh
npm run publish
```

The publisher requires the `r8508271-lang` GitHub account and verifies it through GitHub before fetching or pushing. It checks the origin, existing history, files, and results; commits with **Anonymous Authors** and the anonymous account's noreply email; disables signing and hooks; and uses the verified credential for the push. It never copies another repository's Git history or rewrites existing history.

Use the anonymous account with the GitHub CLI or a local Git credential helper. Never paste tokens into the repository or documentation. Personal paths, credentials, Drive caches, and local configuration must remain untracked.

The previous Drive gallery publishing timer is disabled for this submission snapshot so it cannot overwrite the page. Future updates require a reviewed anonymous publication through the command above.
