"""Region profiles are data, not code (#57).

The test that matters is the second one: a new country is a Markdown file and
a registry row, and selecting it touches no Python.
"""

import re
from pathlib import Path

import pytest

from app.agent import regions
from app.agent.regions import PROFILES_DIR, ProfileRegistryError, load_profiles, select_profile


def test_ro_ppc_ships_and_is_selected_by_provider():
    profile = select_profile("RO", ["Furnizor: PPC Energie Muntenia S.A."])
    assert profile is not None and profile.id == "ro_ppc"
    assert "Certificate verzi" in profile.text and "green_certificates" in profile.text


def test_the_country_default_covers_an_unknown_provider():
    assert select_profile("RO", ["Some Other Supplier SRL"]).id == "ro_ppc"


def test_no_profile_for_a_country_without_one():
    assert select_profile("PT", ["PPC Energie"]) is None
    assert select_profile(None, ["PPC Energie"]) is None


def test_a_second_profile_needs_no_python(tmp_path):
    """Copy the shipped profiles, add a file and a row, and select it."""
    for path in PROFILES_DIR.iterdir():
        if path.is_file():
            (tmp_path / path.name).write_text(path.read_text())
    (tmp_path / "pt_edp.md").write_text("# Region profile: Portugal — EDP\n\n`Termo fixo` → standing_charge\n")
    with (tmp_path / "registry.toml").open("a") as f:
        f.write(
            '\n[[profile]]\nid = "pt_edp"\ncountry = "PT"\nfile = "pt_edp.md"\n'
            'provider_patterns = ["EDP Comercial"]\n'
        )

    profiles = load_profiles(tmp_path)
    profile = select_profile("PT", ["EDP Comercial, S.A."], profiles=profiles)
    assert profile.id == "pt_edp" and "Termo fixo" in profile.text
    # The existing country is unaffected, and a PT bill from an unlisted
    # provider gets no profile — PT has no country_default.
    assert select_profile("RO", ["PPC Energie"], profiles=profiles).id == "ro_ppc"
    assert select_profile("PT", ["Other"], profiles=profiles) is None


def test_the_loader_names_no_country():
    """The guard against the first instinct on seeing a second country."""
    source = Path(regions.__file__).read_text()
    for profile in load_profiles():
        assert not re.search(rf"\b{profile.country}\b", source), profile.country
        assert profile.id not in source


def test_two_defaults_for_one_country_are_refused(tmp_path):
    (tmp_path / "a.md").write_text("a")
    (tmp_path / "registry.toml").write_text(
        '[[profile]]\nid="a"\ncountry="RO"\nfile="a.md"\ncountry_default=true\n'
        '[[profile]]\nid="b"\ncountry="RO"\nfile="a.md"\ncountry_default=true\n'
    )
    with pytest.raises(ProfileRegistryError, match="country_default"):
        load_profiles(tmp_path)


def test_a_row_naming_a_missing_file_is_refused(tmp_path):
    (tmp_path / "registry.toml").write_text('[[profile]]\nid="a"\ncountry="RO"\nfile="nope.md"\n')
    with pytest.raises(ProfileRegistryError):
        load_profiles(tmp_path)


def test_profiles_hold_no_personal_data():
    """Labels and vocabulary only: no long digit runs (customer codes, POD
    codes, meter serials, invoice numbers) and no e-mail addresses."""
    for path in PROFILES_DIR.glob("*.md"):
        text = path.read_text()
        assert not re.search(r"\d{6,}", text), path.name
        assert "@" not in text, path.name
