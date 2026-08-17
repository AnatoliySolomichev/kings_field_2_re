# Outside sources

Findings taken from other people's work. Anything that has since been checked
against our own disc or RAM has moved into [FORMATS.md](FORMATS.md) with the
evidence attached; what is left here is **unverified for SLUS-00255** and should
be treated as a hypothesis, not a fact.

A note on numbering, because it is the easiest way to read one of these sources
wrong. The series is numbered differently in Japan and the West:

| Japan | West | Disc | Ours? |
| --- | --- | --- | --- |
| King's Field | never released | SLPS-00017 | no |
| King's Field II | *King's Field* (US) | SLUS-00158 | no |
| King's Field III | ***King's Field II*** (US) | **SLUS-00255** | **yes** |
| King's Field IV | King's Field: The Ancient City | SLUS-01324 | no |

Projects use the Japanese numbering. When KingsFieldRE says "KF2" it means the
first US game, not ours; ours is its `KF3U`.

## Sources

| What | Where | Covers our disc? |
| --- | --- | --- |
| KingsFieldRE — tools, notes | [github.com/IvanDSM/KingsFieldRE](https://github.com/IvanDSM/KingsFieldRE) | partly, as `KF3U` |
| KingsFieldRE wiki — formats and structures | [the wiki](https://github.com/IvanDSM/KingsFieldRE/wiki) | no, SLUS-00158 |
| GameShark codes for SLUS-00255 | [gamehacking.org/game/89071](https://gamehacking.org/game/89071) | **yes** |
| King's Field Texture Tool | [romhacking.net utility 1063](https://www.romhacking.net/utilities/1063/) | series-wide |
| Ghidra PSX loader | [lab313ru/ghidra_psx_ldr](https://github.com/lab313ru/ghidra_psx_ldr) | generic PS1 |
| FromSoft Modding Committee | [Discord](https://discord.gg/XgDtp8A9) | where the KF3 knowledge is |

KFModTool identifies SLUS-00255 explicitly and loads its maps and models, but
prints "support for the game you loaded is INCOMPLETE" for it: the name and id
databases in its `kf2/` directory are for SLUS-00158 only, and grepping the
source shows KF3 handling confined to the map and model viewers.

## Already checked, and it held

Listed so nobody re-derives them; the detail is in FORMATS.md.

* the `.T` container layout — matched what we had worked out independently
* the entry checksum, `0x12345678` plus the u32s — verified on every entry of
  seven of our nine archives by `tools/tsum.py`
* the object structure offsets: `Visible` at `+0x00`, `ObjectID` at `+0x06`,
  position at `+0x14`, rotation at `+0x24`, scale at `+0x2c`, gold at `+0x3a`,
  and `0x44` bytes overall. Three of those matching at once is what exposed our
  four-byte record misalignment
* the inventory base `0x800c85e8` — the same address we had found by diffing

## Taken but not verified

**Entity structure**, from the KingsFieldRE wiki, for SLUS-00158. 124 bytes.
Offered as a starting hypothesis for the 120-byte records in `FDAT.T` entry
`3n + 1` and for the live monster records, both of which are undecoded here.
The object structure needed a four-byte shift between the two games, so expect
this one to need adjusting too.

| Offset | Field |
| --- | --- |
| +0x00 | disabled, false only when `0xff` |
| +0x01 | mesh id |
| +0x02 | entity class |
| +0x06 | layer |
| +0x07, +0x08 | tile position |
| +0x09 | alive |
| +0x0a | respawn chance |
| +0x0b | dropped item |
| +0x0c | current animation |
| +0x0e | current state |
| +0x10 | previous state |
| +0x1a | HP |
| +0x22 | parent index — the kraken's head points at its body |
| +0x2c | position |
| +0x40 | rotation, wraps at 4096 |
| +0x48 | scale |
| +0x60 | state pointer |

**Entity states**, from the same project's notes, observed in SLUS-00158:

| Value | State |
| --- | --- |
| `0x01` | wandering |
| `0x02` | taking damage |
| `0x03` | dying |
| `0x04` | melee attack |
| `0x05` | approaching the player |
| `0x0f` | dash |
| `0x17`, `0x18` | secondary attacks |
| `0x19` | casting — archers' arrows are a spell internally |

**Object fields whose names did not survive contact with our game.** The wiki
calls `+0x38` `KeyID` and `+0x3e` `MessageID`. On SLUS-00255 the code says
otherwise: `+0x38` is a gate the pickup handler tests against `0xff`, with
`0xf0`, `0xf1` and `0xfe` selecting different refusals, and `+0x3e` is a flag
whose only test is against zero. Both may still be key and message related, but
neither is a plain id here, so we do not carry the names over. The wiki's
pointer at `+0x40` is an object *index* in our build, not an address.

**Offensive rating layout.** The gamehacking code list gives eight offensive
figures and nine defensive ones. Reading both as 9-wide arrays laid out slash,
blow, stab, dark, holy, fire, earth, wind, water fits the addresses exactly and
implies the list's offensive magic labels are each one slot low. No character
we have snapshotted carries a magic rating, so this is unconfirmed.
