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

    features = {
        "text_density": _clamp(math.log1p(text_length) / math.log1p(6000)),
        "link_density": _clamp(math.log1p(link_count) / math.log1p(120)),
        "internal_ratio": _clamp(internal_ratio),
        "title_signal": _clamp(title_length / 120.0),
        "word_diversity": _clamp(unique_word_ratio),
        "depth_signal": _clamp(depth / 6.0),
    }
    return [features[name] for name in FEATURE_NAMES], features


def build_webpage_feature_circuit(values: List[float], page_label: str) -> QuantumCircuit:
    n_qubits = len(values)
    qc = QuantumCircuit(n_qubits, name="page_encode")

    for i, value in enumerate(values):
        theta = math.pi * value
        phi = math.pi * (1.0 - value)
        qc.ry(theta, i)
        qc.rz(phi, i)

    for i in range(n_qubits - 1):
        qc.cx(i, i + 1)
    qc.cx(n_qubits - 1, 0)

    for i, value in enumerate(values):
        qc.rx(math.pi * (0.5 + value / 2.0), i)

    qc.barrier()
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
