"""Design variables of the surrogate geometry family (docs/design_parameters.md §4).

One table for everything that builds, samples or plots designs: the ID used in the
docs, the CarParams field it sets, unit, G1 v5 baseline and the proposed range. The
ranges are the 2026-10-23 draft (not decided); build checks (scripts/build_designs.py)
show which of them are legal.

A design is a dict {field or ID: value}; anything left out stays at the baseline.
Every design is a G1 car with the detail parts on (`build_car.py --fia`), in corner
mode (Z mode); the straight mode is a separate pairing, not a variable.
"""
from dataclasses import dataclass, fields

from cad.car2026 import CarParams


@dataclass(frozen=True)
class Var:
    id: str          # docs ID (FW1, ...)
    field: str       # CarParams field
    unit: str
    lo: float
    hi: float
    group: str
    label: str       # short Korean description

    @property
    def baseline(self):
        return getattr(BASE, self.field)


# G1 v5 = build_car.py --half --fia
BASE = CarParams(geom_level="G1", halo=True, suspension=True, wake_boards=True, mirrors=True)

VARIABLES = (
    Var("FW1", "fw_aoa_out", "deg", -3.0, 3.0, "front wing", "앞날개 바깥(Y 300~) 받음각"),
    Var("FW2", "fw_flap_delta", "deg", -4.0, 4.0, "front wing", "앞날개 플랩 2장 각"),
    Var("FW3", "fw_twist_tip", "deg", -3.0, 3.0, "front wing", "앞날개 끝(Y 450~670) 비틀림"),
    Var("FW4", "fw_flap_chord", "-", 0.85, 1.15, "front wing", "앞날개 플랩 코드 배율"),
    Var("FW5", "fw_camber", "-", 0.04, 0.08, "front wing", "앞날개 단면 캠버"),
    Var("RW1", "rw_main_aoa", "deg", -3.0, 1.0, "rear wing", "뒷날개 주날개 각"),
    Var("RW2", "rw_flap_delta", "deg", -5.0, 1.0, "rear wing", "뒷날개 플랩 2장 각"),
    Var("RW3", "rw_tip_rise", "mm", -5.0, 15.0, "rear wing", "뒷날개 바깥(Y 300~) 앞전 높이"),
    Var("RW4", "rw_camber", "-", 0.04, 0.07, "rear wing", "뒷날개 플랩 캠버"),
    Var("SP1", "sp_undercut", "mm", -60.0, 40.0, "sidepod / engine cover", "사이드포드 아랫면(언더컷) 높이"),
    Var("SP2", "sp_inlet_top", "mm", -50.0, 30.0, "sidepod / engine cover", "사이드포드 흡입구 윗면 높이"),
    Var("EC1", "ec_downwash", "mm", -60.0, 30.0, "sidepod / engine cover", "엔진커버 다운워시 윗면 높이"),
    Var("EC2", "ec_waist", "-", 0.85, 1.10, "sidepod / engine cover", "엔진커버 허리 폭 배율"),
    Var("EC3", "ec_max_width", "mm", -80.0, 20.0, "sidepod / engine cover", "엔진커버 최대 반폭"),
    Var("FB1", "fb_yaw", "deg", 16.0, 22.0, "floor board", "플로어 보드 안쪽 기울기"),
    Var("FB2", "fb_x", "mm", 700.0, 900.0, "floor board", "플로어 보드 앞전 X"),
    Var("FB3", "wb_chord", "mm", 300.0, 500.0, "floor board", "플로어 보드 코드"),
    Var("FB4", "fb_camber", "-", 0.00, 0.04, "floor board", "플로어 보드 캠버"),
    Var("RH1", "ride_height_front", "mm", 20.0, 45.0, "setup", "앞 라이드 하이트"),
    Var("RH2", "ride_height_rear", "mm", 60.0, 110.0, "setup", "뒤 라이드 하이트"),
)
BY_ID = {v.id: v for v in VARIABLES}
BY_FIELD = {v.field: v for v in VARIABLES}
_FIELDS = {f.name for f in fields(CarParams)}


def resolve(name):
    """CarParams field for a docs ID or a field name."""
    if name in BY_ID:
        return BY_ID[name].field
    if name in BY_FIELD or name in _FIELDS:
        return name
    raise KeyError(f"unknown design variable {name!r}")


def params(design=None):
    """CarParams of a design {ID or field: value}; the rest stays at G1 v5."""
    over = {resolve(k): float(v) for k, v in (design or {}).items()}
    return BASE.with_(**over)


def vector(p):
    """{ID: value} of every design variable of a CarParams."""
    return {v.id: getattr(p, v.field) for v in VARIABLES}


def screening():
    """Baseline plus each variable at its two range ends: 2 * 20 + 1 designs."""
    out = [("base", {})]
    for v in VARIABLES:
        out.append((f"{v.id}_lo", {v.id: v.lo}))
        out.append((f"{v.id}_hi", {v.id: v.hi}))
    return out
