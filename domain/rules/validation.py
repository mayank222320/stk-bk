from typing import Literal

from pydantic import BaseModel, root_validator


class VetoContext(BaseModel):
    binding_inputs_status: Literal["OK", "STALE", "UNAVAILABLE"] = "OK"
    price_divergence_pct: float | None = None
    regime: str | None = None
    days_to_results: int | None = None
    setup_type: str | None = None
    adx: float | None = None
    trade_direction: Literal["LONG", "SHORT"] = "LONG"
    weekly_trend: Literal["UP", "DOWN", "SIDEWAYS"] | None = None
    structure: str | None = None
    rs_rating: float | None = None
    turnover_cr: float | None = None
    piotroski_score: int | None = None
    altman_z: float | None = None
    rr_to_t1: float | None = None
    qmaf_gate_failed: bool = False
    heat_cap_breached: bool = False

    # Example of validation for inputs
    @root_validator(pre=True)
    def check_rr_and_levels(cls, values):
        # If R:R is passed, ensure it is positive
        rr = values.get('rr_to_t1')
        if rr is not None and rr < 0:
            raise ValueError("R:R to T1 must be positive")
        return values
