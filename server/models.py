from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator
import json
from pathlib import Path
CATALOG = json.loads((Path(__file__).parent / 'catalog.json').read_text())
IDS = {int(k) for k in CATALOG}
Group = Literal['world', 'party', 'raid']
class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, allow_inf_nan=False)
class Row(Strict):
    spellId: int
    group: Group
    procs: int = Field(ge=0, le=100_000_000)
    combatProcs: int = Field(ge=0, le=100_000_000)
    combatSeconds: float = Field(ge=0, le=315_576_000)
    @model_validator(mode='after')
    def check(self):
        if self.spellId not in IDS or self.combatProcs > self.procs or (self.combatSeconds == 0 and self.combatProcs != 0):
            raise ValueError('invalid effect or counters')
        return self
class Event(Strict):
    spellId: int
    procs: int = Field(ge=0, le=1_000_000)
    eligible: bool
    @model_validator(mode='after')
    def check(self):
        if self.spellId not in IDS: raise ValueError('unknown effect')
        return self
class Segment(Strict):
    id: int = Field(ge=1, le=2**53-1)
    group: Group
    seconds: float = Field(ge=0, le=604800)
    status: Literal['active','complete']
    rows: list[Event] = Field(max_length=200)
    @model_validator(mode='after')
    def check(self):
        if len({r.spellId for r in self.rows}) != len(self.rows): raise ValueError('duplicate effect')
        return self
class Upload(Strict):
    schemaVersion: Literal[1]
    addonVersion: str = Field(pattern=r'^\d{1,3}\.\d{1,3}\.\d{1,3}$')
    characterId: str
    collectionId: str
    sequence: int = Field(ge=1, le=2**53-1)
    exportedAt: int = Field(ge=946684800, le=4102444800)
    privacy: Literal['anonymous','named']
    name: str | None = Field(default=None, min_length=2, max_length=40)
    realm: str | None = Field(default=None, min_length=1, max_length=80)
    historyTruncated: bool
    totals: list[Row] = Field(min_length=1,max_length=600)
    segments: list[Segment] = Field(max_length=301)
    @model_validator(mode='after')
    def check(self):
        for key in (self.characterId,self.collectionId):
            if str(UUID(key)) != key: raise ValueError('invalid UUID')
        if self.privacy == 'anonymous' and (self.name is not None or self.realm is not None): raise ValueError('anonymous data contains names')
        if self.privacy == 'named':
            if not self.name or not self.realm: raise ValueError('missing name')
            if any(not(c.isalpha() or c in " '-") for c in self.name + self.realm): raise ValueError('invalid name')
        keys={(r.spellId,r.group) for r in self.totals}
        if len(keys)!=len(self.totals): raise ValueError('duplicate total')
        if len({s.id for s in self.segments})!=len(self.segments): raise ValueError('duplicate segment')
        sums={}
        active=0
        for segment in self.segments:
            active += segment.status=='active'
            for event in segment.rows:
                key=(event.spellId,segment.group)
                if key not in keys: raise ValueError('history lacks total')
                v=sums.setdefault(key,[0,0,0.0])
                v[0]+=event.procs
                if event.eligible:
                    v[1]+=event.procs; v[2]+=segment.seconds
        if active>1: raise ValueError('multiple active segments')
        for row in self.totals:
            v=sums.get((row.spellId,row.group),[0,0,0.0])
            if v[0]>row.procs or v[1]>row.combatProcs or v[2]>row.combatSeconds+0.01: raise ValueError('inconsistent history')
        return self
