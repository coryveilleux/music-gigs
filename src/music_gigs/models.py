from __future__ import annotations

from pydantic import BaseModel, Field


class Member(BaseModel):
    id: str
    name: str


class BandConfig(BaseModel):
    name: str
    slug: str | None = None
    members: list[Member] = Field(default_factory=list)


class Song(BaseModel):
    title: str
    original_artist: str = ""
    key: str
    lead_singer: str = ""
    duration_seconds: int = 0
    active: bool = True
    reference_artists: list[str] = Field(default_factory=list)
    writers: list[str] = Field(default_factory=list)
    structure: str | None = None
    chords: str | None = None
    lyrics: str | None = None
    verse_hints: list[str] = Field(default_factory=list)
    notes: str | None = None


class SongCatalog(BaseModel):
    songs: list[Song] = Field(default_factory=list)


class Band(BaseModel):
    directory: str
    slug: str
    config: BandConfig
    catalog: SongCatalog

    @property
    def name(self) -> str:
        return self.config.name

    def member_name(self, member_id: str) -> str:
        for member in self.config.members:
            if member.id == member_id:
                return member.name.strip()
        return member_id

    def member_first_name(self, member_id: str) -> str:
        name = self.member_name(member_id)
        return name.split()[0] if name.split() else name


class GigConfig(BaseModel):
    duration_minutes: int = 90
    absent_members: list[str] = Field(default_factory=list)
    tolerance_minutes: int = 5


class ConstraintWarning(BaseModel):
    rule: str
    message: str
    set_number: int
    song_indices: list[int] = Field(default_factory=list)


class SetListSong(BaseModel):
    song: Song
    set_number: int
    position: int


class SetList(BaseModel):
    songs: list[SetListSong] = Field(default_factory=list)
    warnings: list[ConstraintWarning] = Field(default_factory=list)
    filter_warnings: list[str] = Field(default_factory=list)

    @property
    def sets(self) -> dict[int, list[SetListSong]]:
        result: dict[int, list[SetListSong]] = {}
        for entry in self.songs:
            result.setdefault(entry.set_number, []).append(entry)
        return result

    @property
    def total_duration_seconds(self) -> int:
        return sum(entry.song.duration_seconds for entry in self.songs)


class ExportColumn(BaseModel):
    id: str
    label: str
    default: bool = True


EXPORT_COLUMNS: list[ExportColumn] = [
    ExportColumn(id="set_number", label="Set", default=True),
    ExportColumn(id="lead_singer", label="Lead Singer", default=True),
    ExportColumn(id="key", label="Key", default=True),
    ExportColumn(id="title", label="Title", default=True),
    ExportColumn(id="original_artist", label="Original Artist", default=False),
    ExportColumn(id="duration", label="Duration", default=False),
    ExportColumn(id="notes", label="Notes", default=False),
]

DEFAULT_TEXT_TEMPLATE = "{lead_singer} - {key} - {title}"
