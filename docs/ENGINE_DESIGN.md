# neuroSim engine design (CS1)

This is the guide for whoever builds the simulation and vulnerability model.
It explains what the engine computes, how, and why each choice was made, so
you can defend every number in front of a judge and change a decision
knowingly. The code stubs in `backend/neurosim/engine/` follow this document
section by section.

**One-paragraph version.** We treat the fly brain as a weighted, directed
graph of ~139k neurons. We remove (or weaken) the output of the "seed"
neurons, the dopamine neurons that published studies show die in a fly
model of a Parkinson's gene. We measure, for every other neuron, how much of
its input disappears, directly and within 3 synaptic steps. We average that
per brain region and per cell type, and compare each average against 200
runs that remove the same number of random dopamine neurons. Regions that
lose much more than chance are reported as vulnerable.

```
gene ──► seed neurons ──► deficit x0 ──► propagate over A (3 hops) ──► per-neuron impact
                                                                          │
                          200 random DA seed sets ──► same pipeline ──► null distribution
                                                                          │
                                         per-region / per-cell-type mean ─┴─► z, p, q ─► ranked list
```

---

## 1. The question the engine answers

> "Which brain regions and cell types get an unusually large share of their
> input from the neurons at risk?"

That is **structural dependency**. It is not activity, behaviour, or disease
progression. Every design choice below keeps the answer to that question
honest, simple, and reproducible. When a choice would make the model "more
realistic" but harder to explain or check, we skip it for the MVP and note it
in section 10.

---

## 2. The graph

| Decision | Choice | Why |
| --- | --- | --- |
| Node | One neuron (FlyWire root ID) | Cell types are not uniform; neuron level keeps that detail. We aggregate to groups after computing, never before. |
| Edge | Presynaptic → postsynaptic neuron pair | Direction matters: a lost neuron only affects its targets. |
| Edge weight | Synapse count, summed over all neuropils for the pair | The feather file splits a pair by neuropil. A pair with 3 + 3 synapses in two neuropils is a real 6-synapse connection. |
| Threshold | Keep pairs with ≥ 5 synapses, applied **after** summing | FlyWire convention: below ~5, many connections are detection errors. Summing first avoids dropping real, spread-out connections. |
| Proofread only | Yes (`proofread_connections_783`) | Unproofread fragments add noise and are not real neurons. |
| Sign | Ignored in the MVP | See section 5. Kept in the data for the stretch. |

Each neuron's **region** is the neuropil where it receives the most
synapses (computed before thresholding). Why input, not output: a
perturbation removes input, so the place a neuron is hit is where its
dendrites are.

---

## 3. Edge weights: input normalization

We do not propagate raw synapse counts. We convert them to **input fractions**:

```
A[j, i] = W[i, j] / in_j        in_j = total synapses onto neuron j
```

`A[j, i] = 0.3` means "30% of neuron j's input comes from neuron i".
Every row of A sums to 1 (or 0 for neurons with no input).

| Option | What it answers | Why not (or why) |
| --- | --- | --- |
| Raw counts | "How many synapses are lost?" | Big neurons with thousands of inputs dominate every ranking. Not comparable across neurons. |
| Output-normalized (divide by the source's total output) | "Where does i's output go?" | Answers a spreading question, not a dependency question. A hub that sends 1% of its output to j would look unimportant even if it is 90% of j's input. |
| **Input-normalized (chosen)** | "How much of j's input is lost?" | Directly the dependency question. Bounded 0–1, so scores are interpretable and comparable. The same idea underlies recent connectome "influence" analyses. |

---

## 4. Perturbation

A perturbation sets each neuron's **output factor** m (1 healthy, 0 knocked
out, 1 − s at strength s). The engine uses the **deficit** x0 = 1 − m, which
is non-zero only at seeds.

| Mode | Deficit at seeds | Kept? |
| --- | --- | --- |
| Knockout | 1 | Yes |
| Reduce output by s | s | Yes |
| Reduce overall connectivity (inputs and outputs) | same as reduce output | **Dropped.** In a linear model nothing downstream sees a seed's inputs, so it always gives the same answer as "reduce output". Two buttons with identical results would confuse users and judges. |
| Synaptic impairment by edge class | needs signed edges | Stretch, with section 5's signed model. |

Because the model is linear (section 5), reducing output by 50% halves every
impact score exactly. That is a property to state, not a bug: the ranking of
regions does not change with strength, only the magnitude. The UI should say
so.

---

## 5. Propagation

```
h1 = A · x0                 direct: share of each neuron's input lost
h2 = A · h1                 share of input coming from neurons that were hit
h3 = A · h2
I  = h1 + d·h2 + d²·h3      impact score (d = decay = 0.5, K = 3 hops)
```

**Worked example** (this exact graph is in `tests/test_engine_toy.py`):

```
S ─30─► A ◄─10─ X           S is the seed. X and C are healthy inputs.
        │
       20
        ▼
C ─20─► B ─10─► D           S ─4─► E is dropped (below 5 synapses)
                            X ─10─► E
```

| Neuron | Input | Share from upstream | h1 | h2 | h3 | I (d = 0.5) |
| --- | --- | --- | --- | --- | --- | --- |
| A | 40 | 75% from S | 0.75 | 0 | 0 | 0.75 |
| B | 40 | 50% from A | 0 | 0.375 | 0 | 0.1875 |
| D | 10 | 100% from B | 0 | 0 | 0.375 | 0.09375 |
| E | 10 | 100% from X | 0 | 0 | 0 | 0 |

Read it as: A loses three quarters of its input. Half of B's input comes from
A, which is 75% compromised, so B is 37.5% compromised one step later. D
depends entirely on B, so it inherits B's 37.5% one step after that, but
counts for less because it is further away.

| Decision | Choice | Why | Revisit if |
| --- | --- | --- | --- |
| Model type | Linear propagation | Transparent (a judge can follow the table above), fast (one sparse multiply per hop), no fitted parameters to defend. | You add the spiking stretch, which replaces this with dynamics. |
| Hops K | 3 | Most of the effect is within 2–3 steps; beyond that, everything in the brain is a little connected to everything and scores flatten. 3 is also easy to say. | Sensitivity check (section 9) shows rankings change a lot between K = 3 and 4. |
| Decay d | 0.5 | Distant effects should count less. 0.5 is a simple halving, easy to explain. | Same as above. |
| Bound | Each hk is in [0, 1] | Rows of A sum to ≤ 1, x0 ≤ 1, so averaging can never exceed 1. I is at most 1 + 0.5 + 0.25 = 1.75. | Never; if you see a value above that, there is a bug. |
| Seeds | Kept in the matrix, excluded from all reported scores | Excluding them from reports avoids trivial "the seeds are hit" results. Keeping them in the matrix keeps the model linear; loops back through seeds are rare and weak. | — |
| Sign | Ignored (MVP) | We measure dependency, not excitation. With dopamine (modulatory) seeds, a sign at the first step is not even defined. | Signed stretch: split A into excitatory (acetylcholine) and inhibitory (GABA, glutamate as a simplification) parts and report both losses separately, never netted. |

---

## 6. From neurons to vulnerable groups

People reason about brain regions and cell types, not 139k IDs. We report at
four levels: **super region** (mushroom body, central complex; the Sankey
and the headline), **region** (FlyWire neuropil), **cell type** (what a lab
would test), **super class** (central, descending, sensory, ...).

| Decision | Choice | Why |
| --- | --- | --- |
| Group score | **Mean** impact over non-seed neurons in the group (also mean direct) | A sum ranks big regions first just for being big. The mean asks "how hard is a typical neuron here hit?" and is comparable across sizes. |
| Breadth | `n_strong_hits`: neurons with direct ≥ 0.10 | Shows whether a high mean is many neurons hit a little or a few hit hard. |
| Small groups | Not ranked below 5 neurons | Means of 1–4 neurons are noise and would crowd the top of the list. |
| Unlabelled neurons | Group "unlabelled", never ranked | Still part of the wiring, but not a result anyone can act on. |

**Disruption score** (one headline number):

```
D = Σ in_j · I_j / (Σ in_j · I_max)       over non-seed neurons j, I_max = 1.75
```

An input-weighted, brain-wide average impact scaled to 0–1. In absolute
terms it is small, because most of the brain is far from any seed (the toy
graph gives 0.22; the real brain will give well under 0.01). The meaningful
part is its z-score against random seeds, so the UI shows "disruption: 3.1×
the random spread" rather than "0.4%".

---

## 7. The random baseline: what makes a result real

Without a baseline, every run "finds" the regions that are densely connected
to anything. The baseline asks: **would random neurons like these do the same?**

**Null model:** 200 random sets of **dopaminergic** neurons, each the same
size as the real seed set, run through the identical pipeline (same mode,
strength, hops, decay).

| Null | What a high z then means | Use |
| --- | --- | --- |
| Random neurons of any type | "Hit more than random neurons would" | Shown as a secondary "vs whole brain" number. Weak: dopamine neurons as a class project heavily to the mushroom body, so every PD gene would "discover" it. |
| **Random DA neurons (chosen)** | "Hit more than dopamine neurons in general" | Headline. This isolates what is specific to the clusters this gene kills. |
| Degree-matched random neurons | Controls for seeds being unusually well connected | Stretch, if a judge asks. |

**Statistics per group:**

```
z = (observed − mean_null) / sd_null
p = (1 + #null ≥ observed) / (1 + 200)          empirical, one-sided
q = Benjamini–Hochberg FDR over all ranked groups at that level
above chance  ⇔  q < 0.05 and z > 0
```

Why FDR: there are ~80 regions and thousands of cell types. At p < 0.05,
several would light up by luck; BH keeps the expected share of false hits at
5%. With 200 draws the smallest possible p is 1/201 ≈ 0.005, which is enough
to pass FDR for a handful of strong groups. If a judge asks for more
precision, raise draws to 1000; it is still seconds.

**Speed:** stack the 200 deficit vectors as columns of one sparse matrix
(n × 200) and propagate once. Each hop is a single sparse–dense multiply.
Fix the random seed so reruns are identical.

---

## 8. Outputs for the screens and the agent

- **Sankey** (seed cluster → super region): run propagation once per seed
  cluster. Because the model is linear, the per-cluster impacts add up
  exactly to the total, so the bands are an honest decomposition, not an
  approximation.
- **Neuron subgraph:** seeds plus top neurons by impact, ≤ 200 nodes, layout
  computed once on the healthy graph and reused for the perturbed view.
- **Top paths:** for "why is this neuron hit?", the strongest seed → … →
  neuron paths, path strength = product of A weights. Directly readable:
  "PPL101 provides 41% of MBON01's input."
- **Gene comparison:** Spearman correlation of the two runs' group
  **z-scores**, plus shared and unique above-chance groups. Compare z-scores,
  not raw impact, because PINK1 and PRKN seed different numbers of neurons
  and raw impact grows with seed count.
- **Leave-one-cluster-out (stretch):** rerun without each seed cluster; the
  one whose removal drops the top z-scores most is the bottleneck. This is
  the agent's natural follow-up experiment.

---

## 9. Validation and sanity checks

**Built-in validation (hours 20–32, with Bio).** Seed with the PAM neurons
from Riemensperger et al. 2013, where α-synuclein in ~15 PAM neurons per
hemisphere weakens their input to the mushroom body β′ lobe, which is needed
for climbing. Check that β′-lobe regions and their output neurons rank high
above chance. If yes: "the engine recovers a known Parkinson's-model result."
If no: find out why before the demo (wrong cell types? region labels?).

**Sensitivity check.** Rerun PINK1 with threshold ∈ {5, 10}, decay ∈ {0.3,
0.5, 0.7}, hops ∈ {2, 3, 4}. Report the Spearman correlation of super-region
z-scores against the default. If all are above ~0.8, say "results are stable
to model settings." If not, the headline claims must be softened.

**Sanity checks to automate (tests):**

1. Every row of A sums to 1 or 0.
2. Toy graph reproduces the table in section 5 exactly.
3. Reduce output at 0.5 gives exactly half of knockout.
4. Sum of per-cluster Sankey impacts equals the total impact.
5. Seeding random DA neurons gives median z ≈ 0 against the DA null.
6. Same request twice gives byte-identical results.

---

## 10. Known limitations (say them before a judge does)

- **Dopamine is partly volume transmission.** It can act on cells it has no
  synapse with. Synapse counts understate and mislocate its reach.
- **Pink1 and parkin damage is largely mitochondrial and cell-intrinsic.**
  We model only what happens when those neurons stop contributing output.
- **Linear, unsigned, static.** No excitation vs inhibition, no dynamics,
  no compensation or plasticity.
- **Seeds are only as good as the papers.** Different studies report
  different clusters; that uncertainty is shown, not removed.
- **One brain.** FAFB is a single female fly; individual wiring varies.
- **Fly, not human.** Results are hypotheses about fly circuits.

---

## 11. Build order for CS1

| Hours | Build | Checkpoint |
| --- | --- | --- |
| 0–4 | `prep/build_dataset.py`, `engine/graph.py` | Matrix loaded; row-sum test passes; PPL1 and PAM types found |
| 4–8 | `perturb.py`, `propagate.py`, toy tests | Toy table reproduced; a hand-picked PPL1 seed set gives a non-empty impact vector |
| 8–14 | `vulnerability.py`, `baseline.py`, `pipeline.run_simulation` | PINK1 run returns ranked super regions with z-scores, end to end in a script |
| 14–20 | Integrate with CS2's API; caching | Full PINK1 run from the UI by hour 20 |
| 20–32 | `subgraph.py`, `compare.py`, validation + sensitivity checks | Sankey and subgraph live; PINK1 vs PRKN comparison; PAM validation result known |
| 32–40 | Signed stretch or leave-one-cluster-out, only if ahead | Feature freeze at 40 |

---

## 12. Decision log

Add a row whenever you change something above, so the pitch and the code
stay in sync.

| Decision | Chosen | Alternatives | Why | Revisit if |
| --- | --- | --- | --- | --- |
| Unit of computation | Neuron | Cell type graph | Keeps heterogeneity | Too slow (it won't be) |
| Threshold | ≥ 5 synapses, after summing neuropils | 0, 10 | FlyWire convention | Sensitivity check fails |
| Weights | Input-normalized | Raw, output-normalized | Answers the dependency question; bounded | — |
| Perturbation modes | Knockout, reduce output | + reduce connectivity | Third is identical in a linear model | Model becomes nonlinear |
| Propagation | Linear, 3 hops, decay 0.5 | Personalized PageRank, spiking model | Explainable, fast | Spiking stretch |
| Sign | Unsigned | Signed | Dependency, not activity | Signed stretch |
| Group score | Mean + strong-hit count | Sum, max | Size-independent | — |
| Null | Random DA neurons, size-matched, 200 | Random neurons, degree-matched | Isolates gene-specific signal | Judge asks for degree control |
| Multiple testing | BH FDR 5% | Bonferroni, none | Standard, not over-strict | — |
