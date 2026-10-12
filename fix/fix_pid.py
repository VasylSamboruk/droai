"""PID used by ACRO/FIX aiming (frame error → stick rate)."""

from __future__ import annotations


class PID:
    def __init__(
        self,
        kp: float,
        ki: float,
        kd: float,
        *,
        out_max: float = 1.0,
        i_max: float = 0.5,
    ) -> None:
        self.kp = float(kp)
        self.ki = float(ki)
        self.kd = float(kd)
        self.out_max = abs(float(out_max))
        self.i_max = abs(float(i_max))
        self._integral = 0.0
        self._prev_err = 0.0
        self._has_prev = False

    def reset(self) -> None:
        self._integral = 0.0
        self._prev_err = 0.0
        self._has_prev = False

    def update(self, err: float, dt: float) -> float:
        if dt <= 0.0:
            dt = 1e-3

        p_term = self.kp * err

        self._integral += err * dt
        i_term = self.ki * self._integral
        if i_term > self.i_max:
            i_term = self.i_max
            if self.ki > 1e-9:
                self._integral = i_term / self.ki
        elif i_term < -self.i_max:
            i_term = -self.i_max
            if self.ki > 1e-9:
                self._integral = i_term / self.ki

        if self._has_prev:
            d_term = self.kd * (err - self._prev_err) / dt
        else:
            d_term = 0.0
            self._has_prev = True
        self._prev_err = err

        out = p_term + i_term + d_term
        return max(-self.out_max, min(self.out_max, out))

    def gains_str(self) -> str:
        return f"{self.kp:.2f}/{self.ki:.2f}/{self.kd:.2f}"
