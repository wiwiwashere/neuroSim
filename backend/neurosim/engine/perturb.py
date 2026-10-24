"""Perturbation modes (CS1). See docs/ENGINE_DESIGN.md, section 4.

STATUS: placeholder. CS1 writes initial_deficit. pipeline.py, the
validation script and the API already call it with the signatures
below, and the tests marked `needs_engine` turn green once it works.

A perturbation is described by one number per neuron, its output factor m:
    m = 1        healthy
    m = 0        knocked out (produces no output)
    m = 1 - s    output reduced by strength s

The engine never uses m directly. It uses the deficit x0 = 1 - m: how much
of each neuron's normal output is missing. Healthy neurons have deficit 0, so
only seeds start with a deficit.

Why only two modes: in a linear propagation model, "reduce overall
connectivity" (scaling a seed's inputs AND outputs) has exactly the same
downstream effect as "reduce output", because nothing downstream sees a seed's
inputs. Offering both would show two buttons that always give the same
answer. "Synaptic impairment by edge class" needs signed edges, so it waits
for the signed stretch.
"""

from __future__ import annotations

import numpy as np

from neurosim.models import PerturbationMode


def initial_deficit(
    n_neurons: int,
    seed_positions: np.ndarray,
    mode: PerturbationMode,
    strength: float = 1.0,
) -> np.ndarray:
    """Return x0, a length-n vector: deficit at each seed, 0 elsewhere.

    knockout       -> 1.0 at seeds (strength ignored)
    reduce_output  -> strength at seeds (0.5 = half the output is lost)

    Raise ValueError for an empty seed set; an empty run must never look like
    "no effect".
    """
    raise NotImplementedError("CS1: initial_deficit")
