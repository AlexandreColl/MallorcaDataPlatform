"""Vote: a value is flagged when enough of the other detectors flag it."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from core.anomaly.base import ENTITY_SCORE_COLUMNS, Detector

if TYPE_CHECKING:
    from collections.abc import Sequence


class Vote(Detector):
    """Combines detectors that fail on different things.

    With ``min_votes: 1`` it is their union (a value any of them flags), with a majority it only keeps what they
    agree on. ``score`` is the number of detectors that flag the value and ``threshold`` the votes it needs, so
    the result fits ``silver.anomalies`` like any other detector. ``expected`` is the first member's that has one.
    """

    name = "vote"

    def __init__(self, members: Sequence[Detector], min_votes: int = 1) -> None:
        if not members:
            msg = "a vote needs at least one detector"
            raise ValueError(msg)
        if not 1 <= min_votes <= len(members):
            msg = f"min_votes must be between 1 and the {len(members)} members, not {min_votes}"
            raise ValueError(msg)
        self.members = list(members)
        self.min_votes = int(min_votes)

    @property
    def context(self) -> pd.Timedelta:
        """The longest history any member needs."""
        return max(m.context for m in self.members)

    def score_entity(self, observations: pd.DataFrame) -> pd.DataFrame:
        """Score with every member and count, per value, how many flag it."""
        out = observations[["metric", "ts", "value"]].reset_index(drop=True)
        keys = pd.MultiIndex.from_arrays([out["metric"], out["ts"]])
        votes = np.zeros(len(out), dtype=int)
        expected = pd.Series(np.nan, index=out.index)
        for member in self.members:
            scored = member.score_entity(observations).set_index(["metric", "ts"])
            scored = scored[~scored.index.duplicated()].reindex(keys)
            votes += scored["is_anomaly"].fillna(value=False).astype(bool).to_numpy()
            expected = expected.fillna(pd.Series(scored["expected"].to_numpy(dtype=float), index=out.index))
        out = out.assign(expected=expected, score=votes.astype(float), threshold=float(self.min_votes))
        out["is_anomaly"] = votes >= self.min_votes
        return out[list(ENTITY_SCORE_COLUMNS)]
