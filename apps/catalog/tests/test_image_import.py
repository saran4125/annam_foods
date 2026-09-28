"""Importing a folder of photographs. Getting this wrong puts the wrong food
in front of a customer, so it reports rather than guesses."""
import io

import pytest
from django.core.management import call_command
from PIL import Image

from apps.catalog.management.commands.import_menu_images import keys_for, normalise
from apps.catalog.models import MenuItem
from apps.tenancy.context import tenant_context
from apps.tenancy.models import Tenant


def make_image(path):
    Image.new("RGB", (10, 10), (200, 150, 100)).save(path)


@pytest.fixture
def kitchen(db):
    return Tenant.objects.create(slug="annam", name="Annam Foods", status="active")


@pytest.mark.parametrize("filename,dish", [
    ("veg-meals", "Veg Meals"),
    ("Veg_Meals", "Veg Meals"),
    ("veg meals", "Veg Meals"),
    ("VEGMEALS", "Veg Meals"),
    ("idly", "Idly (4)"),      # the count dropped
    ("idly-4", "Idly (4)"),    # the count kept -- both are natural to type
])
def test_filenames_match_dish_names_loosely(filename, dish):
    assert normalise(filename) in keys_for(dish)


def test_different_dishes_do_not_collide():
    assert normalise("Chicken Biryani") not in keys_for("Egg Biryani")


def test_one_file_matching_two_dishes_is_left_alone(db, tmp_path, capsys):
    """'idly.jpg' against both 'Idly (2)' and 'Idly (4)' must not pick one."""
    kitchen = Tenant.objects.create(slug="annam", name="Annam Foods", status="active")
    with tenant_context(kitchen):
        MenuItem.objects.create(name="Idly (2)", price=25)
        MenuItem.objects.create(name="Idly (4)", price=40)
    make_image(tmp_path / "idly.jpg")

    call_command("import_menu_images", tenant="annam", dir=str(tmp_path))

    assert "Ambiguous" in capsys.readouterr().out
    with tenant_context(kitchen):
        assert not any(i.image for i in MenuItem.objects.all())


def test_images_are_attached_to_matching_dishes(kitchen, tmp_path, capsys):
    with tenant_context(kitchen):
        MenuItem.objects.create(name="Veg Meals", price=120)
        MenuItem.objects.create(name="Idly (4)", price=40)
    make_image(tmp_path / "veg-meals.jpg")
    make_image(tmp_path / "idly.png")

    call_command("import_menu_images", tenant="annam", dir=str(tmp_path))

    with tenant_context(kitchen):
        assert MenuItem.objects.get(name="Veg Meals").image
        assert MenuItem.objects.get(name="Idly (4)").image


def test_a_dry_run_changes_nothing(kitchen, tmp_path):
    with tenant_context(kitchen):
        MenuItem.objects.create(name="Veg Meals", price=120)
    make_image(tmp_path / "veg-meals.jpg")

    call_command("import_menu_images", tenant="annam", dir=str(tmp_path), dry_run=True)

    with tenant_context(kitchen):
        assert not MenuItem.objects.get(name="Veg Meals").image


def test_existing_images_are_kept_unless_overwrite(kitchen, tmp_path):
    with tenant_context(kitchen):
        item = MenuItem.objects.create(name="Veg Meals", price=120)
    make_image(tmp_path / "veg-meals.jpg")
    call_command("import_menu_images", tenant="annam", dir=str(tmp_path))
    with tenant_context(kitchen):
        first = MenuItem.objects.get(pk=item.pk).image.name

    make_image(tmp_path / "veg-meals.jpg")
    call_command("import_menu_images", tenant="annam", dir=str(tmp_path))
    with tenant_context(kitchen):
        assert MenuItem.objects.get(pk=item.pk).image.name == first

    call_command("import_menu_images", tenant="annam", dir=str(tmp_path), overwrite=True)
    with tenant_context(kitchen):
        assert MenuItem.objects.get(pk=item.pk).image.name != first


def test_two_files_matching_one_dish_are_left_alone(kitchen, tmp_path, capsys):
    """Guessing between two candidates could put the wrong food on the page."""
    with tenant_context(kitchen):
        MenuItem.objects.create(name="Veg Meals", price=120)
    make_image(tmp_path / "veg-meals.jpg")
    make_image(tmp_path / "Veg_Meals.png")

    call_command("import_menu_images", tenant="annam", dir=str(tmp_path))

    assert "Ambiguous" in capsys.readouterr().out
    with tenant_context(kitchen):
        assert not MenuItem.objects.get(name="Veg Meals").image


def test_unmatched_files_and_dishes_are_reported(kitchen, tmp_path, capsys):
    with tenant_context(kitchen):
        MenuItem.objects.create(name="Curd Rice", price=60)
    make_image(tmp_path / "something-else.jpg")

    call_command("import_menu_images", tenant="annam", dir=str(tmp_path))
    out = capsys.readouterr().out
    assert "Curd Rice" in out          # dish with no photo
    assert "something-else.jpg" in out  # photo with no dish


def test_an_empty_folder_is_an_error(kitchen, tmp_path):
    from django.core.management.base import CommandError
    with pytest.raises(CommandError, match="No images"):
        call_command("import_menu_images", tenant="annam", dir=str(tmp_path))
