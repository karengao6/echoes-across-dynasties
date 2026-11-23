# Research design and one-month implementation plan

## Scope and question

Ask: within a fixed cohort of Tang and Song shi poets, how strongly do stylistic
neighborhoods agree with imagery-context neighborhoods, and how stable is that
agreement under representation and sampling choices? This is exploratory association,
not evidence of direct influence. Choose three primary phrases in advance after a
coverage-only pilot; label additional searches exploratory. Retain a fixed 50-poet
global cohort and report the smaller eligible cohort for each phrase. Never silently
replace poets to make a phrase graph look fuller.

## Risks and controls

1. Genre dominates dynasty if Tang shi is compared to Song ci. Use shi from both
   collections. Uniform five/seven-character lines are measured form categories,
   not sufficient evidence for regulated verse. Do not label them jueju/lüshi
   without validated rules or metadata. Source collection is not a verified poet date.
2. Lexical similarity contains topic as well as style. Name the views lexical,
   function-character, and structural; their combination is an operational proxy
   for style. Explicitly compare lexical-heavy and lexical-light ablations.
3. Equal poem counts do not equal equal text lengths. Primary sample: 100 poems per
   poet, repeated with 10 seeds. Compare 50 and 100, with 200 only on a separately
   reported common eligible cohort. Match observed form and character budgets as
   sensitivity analyses. Review pseudonyms, duplicate attributions, and long-poem effects.
4. Modern pretrained models may miss allusions, archaic senses and names. Treat
   embeddings as a hypothesis to evaluate, not ground truth. Start with character
   TF-IDF contexts; accept a compact encoder only if blinded human evaluation supports it.
5. Phrase presence can trivially drive embeddings. Compare original contexts to
   contexts with the target replaced by a consistent neutral marker. Nearby repeated
   occurrences in one poem are dependent: aggregate within poem before poet pooling.
6. Pairwise similarities are dependent because each poet occurs in many pairs.
   Do not use ordinary independent-pair correlation p-values. Permute poet labels
   of one matrix (both axes together), ideally within dynasty/form strata. Report
   descriptive Spearman correlation and permutation null; repeat across sampling seeds.
   These tests show association, not removal of every literary confound.

## Numerical representations

Fit transforms on the fixed sampled corpus. Keep each feature family's outputs and
metadata so all ablations can be recomputed.

| Family | Representation | Normalization / interpretation |
|---|---|---|
| Function/common characters | Fixed, manually reviewed inventory; counts per 1,000 Han characters | L2 per poet; distinguish function characters from corpus-common content characters |
| Character n-grams | 1–3-gram TF-IDF; fit on poem documents, never concatenate poem boundaries; aggregate poem vectors equally | L2 normalize the poet vector; publish top weighted terms and vocabulary settings |
| Structure | Proportions of 5/7/other-length lines, mean/SD line length, line count, repeated-character fraction, repeated-line fraction, fixed-length-window lexical diversity | Standardize each column across poets, then L2 normalize family; define zero-vector behavior |

Raw type/token ratio is strongly length-dependent. Prefer mean lexical diversity
in fixed 100-character windows; omit/flag poems shorter than the window and report
coverage. Do not invent rhyme/tone or historical pronunciation features.

For L2-normalized families x_f, concatenate sqrt(w_f) * x_f with equal initial
weights summing to one. The dot product then decomposes into weighted family
contributions when all families are nonzero. Explicitly handle missing/zero families
and display actual per-family scores. For standardized structural features, shared
negative deviations contribute too: explain values relative to corpus means, not
as literal presence of a property. Lexical shared-feature products can help interpret a full-dimensional cosine score.

The poet-style page uses a PCA scatterplot with one point per sampled poet, colored
and shaped by source collection. Default to PC1 and PC2 and allow readers to select
any two available nonzero components. Display explained variance on each axis.
The implemented baseline standardizes the seven verse-structure summaries listed
on the page across poets, drops constant columns, and fits PCA on that matrix.
A second view fits a separate PCA on centered single-character rates per 1,000
Han characters, using the same cohort. Keep characters seen in at least 20% of
sampled poets (at least two) and show the strongest positive and negative
loadings on the selected axes. Shared character use may reflect diction or
subject matter. Character n-grams and a reviewed function-character view are
planned extensions. The scatterplot
is exploratory. Keep full-dimensional cosine for the quantitative comparisons
below, since a two-axis projection hides variation in other components.

## Phrase contexts

The browser defaults to simplified and traditional search aliases generated with
OpenCC. It displays the spellings searched, preserves the original verses, and
offers an exact-spelling mode for reproducible literal queries. Reject empty/non-Han
queries. SQLite instr(text, ?) finds candidates for the 50 poets. Verify each
candidate within verse lines, counting non-overlapping literal matches across the
accepted spellings.

Use the matching verse line plus one line on each side, deduplicated per poem.
Report: occurrence count, matching poems, occurrences/10,000 Han characters, and
fraction of poems containing the phrase. Include numerators and denominators.
Use all eligible works for browsing; use the fixed sampled corpus for the primary
statistical comparison. A switch between these corpora must be visible.

Require at least five distinct matching poems per poet, preferably ten in the
primary analysis. Insufficient evidence is missing/NA, never zero similarity.
Frequency estimates remain visible even when contextual similarity is unavailable.

Baseline: context character TF-IDF. Semantic extension: shortlist a small Chinese
encoder and a small multilingual sentence encoder; pin model revision, inspect
license, tokenizer truncation and model card, and measure Mac CPU/MPS memory and
latency. No model has been selected or validated in this starter. Cache vectors by
model revision + preprocessing version + context hash. No fine-tuning this month.

Representation A: L2-normalize each context embedding, average within poem, average
equally across poems, then L2 normalize the poet vector. Report cosine similarity.
Representation B: fit one shared phrase-specific KMeans model across eligible poet
contexts with balanced contributions per poet (fixed seed). Never fit unrelated
clusters separately per poet. Compare K=3,5,8 where sample size permits; label
clusters through inspected exemplars rather than generated authoritative themes.
Use unsmoothed empirical cluster proportions initially and check small-sample
instability. Jensen–Shannon similarity = 1 - scipy.spatial.distance.jensenshannon(p,q,
base=2); this uses the square-root distance, bounded [0,1]. State this convention.
Bootstrap poems within poets for uncertainty; show cluster stability across seeds.

## Experiments and essay evidence

- Within each phrase's common eligible poets, compare upper-triangle global and
  contextual similarity with Spearman correlation and 999 poet-label permutations.
  Report sample sizes and multiple-testing correction for predeclared phrases.
- Compare top-5-neighbor Jaccard overlap across lexical, structural, combined,
  context-TF-IDF, mean embedding, and cluster-distribution views. Use k=min(5,n-1).
- Repeat samples and phrase thresholds 3/5/10; separate cohort-change effects from
  representation changes with a common-cohort analysis.
- Compare within-Tang, within-Song and across-collection pairs, then within a fixed
  measured form. Avoid attributing residual differences solely to dynasty.
- Human evaluation: ~60 context pairs stratified over predicted similarity and
  dynasty, two readers blinded to scores and author names if feasible. Record
  semantic/imagery relation on a 1–5 rubric plus uncertainty and rationale. Pilot
  on 10 separate pairs; report weighted agreement and ranking agreement with model
  scores. Keep model-selection pairs separate from final evaluation pairs. If only
  one reader is available, report that limitation; do not claim inter-rater reliability.
- Inspect both agreeing and disagreeing neighborhoods; literary close readings
  explain where numerical proxies fail. Avoid cherry-picking only successful matches.

Publication figures: (1) identically ordered global/context similarity heatmaps
with NA cells masked, (2) style-vs-context pair scatter with permutation-null inset
and repeated-sampling range, optionally (3) per-poet cluster proportions with counts.
Export vector PDF/SVG and 300dpi PNG; never fabricate experimental results.

## Milestones and target structure

Week 1: run this ingestion component; inspect rejected records and name identities;
freeze cohort; implement `features/{characters,ngrams,structure}.py`,
`similarity/metrics.py`; save feature names, vectors and matrices. Generate the
structural PCA page with `echoes pca`.
Week 2: `preprocessing/contexts.py`, `embeddings/{encode,cache}.py`; exact search,
TF-IDF context baseline, human rubric/pilot, one encoder comparison. Freeze primary
phrases before inspecting cross-view association results.
Week 3: `backend/{app,schemas,queries}.py` with FastAPI; `frontend/` with React,
TypeScript, and two views. Integrate the PCA scatterplot and the phrase-context graph.
Endpoints: GET /poets, /poets/{id}, /poets/pca, /phrases/coverage; POST /graph/phrase
for an explicit representation/query. Add limits and local caching.
No arbitrary model inference on every keystroke. Defer deployment until local MVP works.
Week 4: `evaluation/{agreement,permutation,sensitivity,annotation,figures}.py`;
run ablations and common-cohort controls; write essay with close readings and limitations.

Cut first if time is short: animation, fine-tuning, ci, arbitrary phrase clustering
on demand, complex deployment, and fancy metadata filters. Keep ingestion quality,
three baseline families, two contextual methods for three phrases, the PCA and phrase-context
views, and honest evaluation. Expansion modules listed here are planned, not delivered.
