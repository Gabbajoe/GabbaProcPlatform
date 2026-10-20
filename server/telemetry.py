"""Bounded, numeric combat context; no character/target names or GUIDs."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

STATS = {"meleeCrit", "rangedCrit", "meleeHitModifier", "spellHitModifier", "mainSpeed", "offSpeed", "rangedSpeed", "haste", "strength", "agility", "stamina", "intellect", "spirit"} | {f"spellCrit{i}" for i in range(1, 8)}

class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)

class Equipment(Strict):
    slot: int = Field(ge=1, le=18)
    itemId: int = Field(ge=1, le=10_000_000)
    enchantId: int = Field(ge=0, le=10_000_000)

class Talent(Strict):
    tab: int = Field(ge=1, le=5)
    index: int = Field(ge=1, le=100)
    rank: int = Field(ge=1, le=10)

class Buff(Strict):
    spellId: int = Field(ge=1, le=10_000_000)
    stacks: int = Field(ge=0, le=1000)

class Sample(Strict):
    atMs: int = Field(ge=0, le=604800000)
    stats: dict[str, float] = Field(max_length=20)
    buffs: list[Buff] = Field(max_length=40)

    @model_validator(mode="after")
    def check(self):
        if not set(self.stats) <= STATS or any(not 0 <= v <= 1_000_000 for v in self.stats.values()):
            raise ValueError("invalid character stats")
        return self

class Attack(Strict):
    kind: Literal["swing", "spell", "ranged", "periodic", "cast"]
    spellId: int = Field(ge=0, le=10_000_000)
    hand: Literal["main", "off", "none"]
    outcome: Literal["hit", "crit", "glancing", "cast", "MISS", "DODGE", "PARRY", "BLOCK", "RESIST", "IMMUNE", "EVADE", "DEFLECT", "ABSORB", "REFLECT", "other"]
    count: int = Field(ge=1, le=1_000_000)

class ProcTime(Strict):
    spellId: int = Field(ge=1, le=10_000_000)
    atMs: int = Field(ge=0, le=604800000)

class Telemetry(Strict):
    version: Literal[1]
    fightId: int = Field(ge=1, le=2**53-1)
    classId: int | None = Field(default=None, ge=1, le=11)
    level: int | None = Field(default=None, ge=1, le=60)
    equipment: list[Equipment] = Field(max_length=18)
    talents: list[Talent] = Field(max_length=100)
    samples: list[Sample] = Field(min_length=1, max_length=32)
    attacks: list[Attack] = Field(max_length=256)
    procTimes: list[ProcTime] = Field(max_length=1024)
    targets: int = Field(ge=0, le=500)
    truncated: bool
    samplesTruncated: bool = False

    @model_validator(mode="after")
    def check(self):
        if self.samples[0].atMs != 0 or any(a.atMs > b.atMs for a, b in zip(self.samples, self.samples[1:])):
            raise ValueError("invalid sample order")
        if len({e.slot for e in self.equipment}) != len(self.equipment):
            raise ValueError("duplicate equipment slot")
        if len({(a.kind,a.spellId,a.hand,a.outcome) for a in self.attacks}) != len(self.attacks):
            raise ValueError("duplicate attack counter")
        return self
