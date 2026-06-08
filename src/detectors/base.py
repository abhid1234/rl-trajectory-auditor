"""Detector contract: a callable (traj, corpus) -> DetectorSignal.
Corpus-unaware detectors simply ignore the second argument."""
from __future__ import annotations
from src.models import DetectorSignal


def no_signal(name: str) -> DetectorSignal:
    return DetectorSignal(name=name, fired=False, score=0.0, evidence=[], details={})
