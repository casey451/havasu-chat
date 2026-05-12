"""Pydantic shapes for photo upload API responses."""

from __future__ import annotations

from pydantic import BaseModel


class PhotoUploadResponse(BaseModel):
    photo_id: str
    status: str


class PhotoListItem(BaseModel):
    id: str
    status: str
    is_hero: bool
    display_order: int
    cdn_url: str | None = None
    thumbnail_url: str | None = None
    medium_url: str | None = None
    hero_url: str | None = None
