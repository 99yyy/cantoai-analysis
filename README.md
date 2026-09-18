# iCantonese corpus analysis outputs

Scripts and tables for investigating post-2025 low agreement scores.

## Score definition
`agreement` / "score" = share of syllables with `jp_match` in {exact_default, exact_alt}.
This is model–dictionary consistency, not human accuracy (see PIPELINE.md).

## Key files
- `scripts/audit.py` — read-only process audit (`docs/AUDIT-SPEC.md`; how to run: `scripts/README-audit.md`)
- `analyze_scores_by_year.py` — main reproducible analysis
- `agreement_by_year.csv` / `agreement_by_period.csv`
- `effect_size_period.json`
- `video_agreement_scores.csv` — per-video scores + upload dates
- `lowest_videos_2025plus.csv` / `highest_videos_2025plus.csv`
- `cinema_keyword_split.csv` — title-keyword proxy for archival/cinema content
- `agreement_by_month_2024plus.csv` + `.png`
- `quality_issues.json`, `schema_summary.json`
- plots: `agreement_by_year_AB.png`, `video_agreement_boxplot_by_year.png`, `video_agreement_hist_period.png`

## Data sources
- SQLite: `/workspace/cantoai/corpus/dataset_v2/work/corpus.sqlite`
- Docs: `/workspace/cantoai/corpus/dataset_v2/docs/PIPELINE.md`
