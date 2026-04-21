from __future__ import annotations

import io
import math
from typing import Dict, List, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from qiskit import QuantumCircuit


FEATURE_NAMES = [
    "text_density",
    "link_density",
    "internal_ratio",
    "title_signal",
    "word_diversity",
    "depth_signal",
]

def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))

def extract_features(page: Dict) -> Tuple[List[float], Dict[str, float]]:
    text_length = max(0, int(page.get("text_length", 0)))
    link_count = max(0, int(page.get("link_count", 0)))
    internal_ratio = float(page.get("internal_ratio", 0.0))
    title_length = max(0, int(page.get("title_length", 0)))
    unique_word_ratio = float(page.get("unique_word_ratio", 0.0))
    depth = max(0, int(page.get("depth", 0)))

    # Apply logarithmic and normalization transformations to create diverse features
    # These ensure that different pages produce different encoded values
    features = {
        # Logarithmic density: distinguishes pages with varying text amounts
        "text_density": _clamp(math.log1p(text_length) / math.log1p(6000)),
        # Link density: varies based on number of links on the page
        "link_density": _clamp(math.log1p(link_count) / math.log1p(120)),
        # Internal link ratio: directly from page analysis
        "internal_ratio": _clamp(internal_ratio),
        # Title length normalized: page titles vary significantly
        "title_signal": _clamp(title_length / 120.0),
        # Word diversity: unique word ratio varies per page
        "word_diversity": _clamp(unique_word_ratio),
        # Depth in crawl graph: increases with crawl depth
        "depth_signal": _clamp(depth / 6.0),
    }
    return [features[name] for name in FEATURE_NAMES], features

def build_webpage_feature_circuit(values: List[float], page_label: str) -> QuantumCircuit:
    n_qubits = len(values)
    qc = QuantumCircuit(n_qubits, name="page_encode")

    # Encode feature values into quantum rotations
    for i, value in enumerate(values):
        # Use feature value to create varying rotation angles
        theta = math.pi * value
        phi = math.pi * (1.0 - value)
        qc.ry(theta, i)
        qc.rz(phi, i)

    # Entangle qubits to create correlations between features
    for i in range(n_qubits - 1):
        qc.cx(i, i + 1)
    qc.cx(n_qubits - 1, 0)

    # Additional rotation layer for quantum interference
    for i, value in enumerate(values):
        qc.rx(math.pi * (0.5 + value / 2.0), i)

    qc.barrier()
    # Set global phase based on aggregate feature values
    qc.global_phase = sum(values) / max(1, len(values))
    qc.metadata = {"page": page_label}
    return qc

def circuit_png_bytes(qc: QuantumCircuit) -> bytes:
    fig = qc.draw(output="mpl", fold=-1, idle_wires=False)
    fig.set_size_inches(12, 2.8)
    fig.tight_layout()
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=180, bbox_inches="tight")
    plt.close(fig)
    return buffer.getvalue()