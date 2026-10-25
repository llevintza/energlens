"""Reads the region profiles in app/agent/profiles/ (#57).

This module knows how to *find* a profile, never what one says. Everything
country- or provider-specific lives in ``profiles/registry.toml`` and the
Markdown files it names, so a second country is a file and a registry row —
there is deliberately no country name anywhere in this module.
"""

import tomllib
from dataclasses import dataclass
from pathlib import Path

PROFILES_DIR = Path(__file__).resolve().parent / "profiles"


@dataclass(frozen=True)
class Profile:
    id: str
    country: str
    text: str
    provider_patterns: tuple[str, ...] = ()
    country_default: bool = False

    def matches_provider(self, hint: str) -> bool:
        hint = hint.casefold()
        return any(p.casefold() in hint for p in self.provider_patterns)


class ProfileRegistryError(ValueError):
    """registry.toml is malformed or names a file that is not there."""


def load_profiles(directory: Path = PROFILES_DIR) -> list[Profile]:
    registry = directory / "registry.toml"
    rows = tomllib.loads(registry.read_text()).get("profile", [])
    profiles: list[Profile] = []
    defaults: set[str] = set()
    for row in rows:
        try:
            country = row["country"].upper()
            path = directory / row["file"]
            profile = Profile(
                id=row["id"],
                country=country,
                text=path.read_text().strip(),
                provider_patterns=tuple(row.get("provider_patterns", ())),
                country_default=bool(row.get("country_default", False)),
            )
        except (KeyError, OSError) as exc:
            raise ProfileRegistryError(f"{registry}: bad [[profile]] row {row!r}: {exc}") from exc
        if profile.country_default:
            if country in defaults:
                raise ProfileRegistryError(
                    f"{registry}: more than one country_default profile for {country}"
                )
            defaults.add(country)
        profiles.append(profile)
    ids = [p.id for p in profiles]
    if len(ids) != len(set(ids)):
        raise ProfileRegistryError(f"{registry}: duplicate profile id in {ids}")
    return profiles


def select_profile(
    country_code: str | None,
    provider_hints: list[str],
    *,
    profiles: list[Profile] | None = None,
) -> Profile | None:
    """The profile for this place and bill, or None.

    ``provider_hints`` is free text that may name the provider — the first page
    of the bill, the prior bill's provider name. A provider match beats the
    country default; another country's profile is never used.
    """
    if not country_code:
        return None
    if profiles is None:
        profiles = load_profiles()
    candidates = [p for p in profiles if p.country == country_code.upper()]
    for profile in candidates:
        if any(profile.matches_provider(hint) for hint in provider_hints if hint):
            return profile
    return next((p for p in candidates if p.country_default), None)
