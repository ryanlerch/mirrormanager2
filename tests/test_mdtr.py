"""
mirrormanager2 tests for the `Move Devel To Release` (MDTL) script.
"""

import os

import pytest
import sqlalchemy as sa
from click.testing import CliRunner

import mirrormanager2.lib
import mirrormanager2.lib.model as model
from mirrormanager2.utility import move_devel_to_release

FOLDER = os.path.dirname(os.path.abspath(__file__))


@pytest.fixture()
def configfile(tmp_path):
    path = tmp_path.joinpath("mirrormanager2_tests.cfg").as_posix()
    contents = f"""
SQLALCHEMY_DATABASE_URI = 'sqlite:///{tmp_path.as_posix()}/test.sqlite'
import os
DB_ALEMBIC_LOCATION = os.path.join("{FOLDER}", "..", "mirrormanager2", "lib", "migrations")


# Specify whether the crawler should send a report by email
CRAWLER_SEND_EMAIL =  False

    """
    with open(path, "w") as stream:
        stream.write(contents)
    return path


@pytest.fixture()
def command_args(configfile):
    return ["-c", configfile, "--version=27", "--category=Fedora Linux"]


def run_command(args):
    runner = CliRunner()
    return runner.invoke(move_devel_to_release.main, args)


def test_mdtr_no_data_empty_db(command_args, db):
    """Test the mdtr script without the appropriate data in the
    database.
    """
    result = run_command(command_args)
    assert result.exit_code == 1
    assert (
        result.output
        == "Error: Category 'Fedora Linux' not found, exiting.\nAvailable categories:\n"
    )


def test_mdtr_no_data(command_args, db, base_items, directory, category, categorydirectory):
    """Test the mdtr script without the appropriate data in the
    database.
    """
    result = run_command(command_args)

    assert result.exit_code == 1
    assert result.output == "Error: Version 27 not found for product Fedora\n"


def test_mdtr_no_data_with_version(
    command_args, base_items, directory, category, categorydirectory, version
):
    """Test the mdtr script without the appropriate data in the
    database.
    """
    result = run_command(command_args)
    assert result.exit_code == 0
    assert result.output == ""


def test_mdtr(command_args, db, base_items, directory, category, categorydirectory, version):
    """Test the mdtr script."""
    item = model.Directory(
        name="pub/fedora/linux/releases/26/Everything/x86_64/os",
        readable=True,
    )
    db.add(item)
    item = model.Directory(
        name="pub/fedora/linux/releases/26/Everything/armhfp/os",
        readable=True,
    )
    db.add(item)
    item = model.Directory(
        name="pub/fedora-secondary/releases/26/Everything/ppc64le/os",
        readable=True,
    )
    db.add(item)
    item = model.Directory(
        name="pub/fedora-secondary/releases/26/Everything/sources/os",
        readable=True,
    )
    db.add(item)
    item = model.Directory(
        name="pub/fedora/linux/development/27/Everything/x86_64/os",
        readable=True,
    )
    db.add(item)
    item = model.Directory(
        name="pub/fedora/linux/releases/27/Everything/x86_64/os",
        readable=True,
    )
    db.add(item)

    item = model.Repository(
        name="pub/fedora/linux/development/27/Everything/x86_64/os",
        prefix="fedora-27",
        version_id=3,
        arch_id=3,
        directory_id=14,
        category_id=1,
    )
    db.add(item)
    item = model.Repository(
        name="pub/fedora/linux/releases/26/Everything/x86_64/os",
        prefix=None,
        version_id=1,
        arch_id=3,
        directory_id=10,
        category_id=1,
    )
    db.add(item)

    item = model.Category(
        name="Fedora Secondary Arches",
        product_id=2,
        canonicalhost="http://download.fedora.redhat.com",
        topdir_id=1,
        publiclist=True,
    )
    db.add(item)

    db.commit()

    # Check before running the script

    results = mirrormanager2.lib.get_repositories(db)
    assert len(results) == 2

    results = db.execute(sa.select(model.Directory)).scalars().all()
    # create_directory creates 9 directories
    # we create 6 more here, 9+6=15
    assert len(results) == 15
    assert results[9].name == "pub/fedora/linux/releases/26/Everything/x86_64/os"
    assert results[10].name == "pub/fedora/linux/releases/26/Everything/armhfp/os"
    assert results[11].name == "pub/fedora-secondary/releases/26/Everything/ppc64le/os"
    assert results[12].name == "pub/fedora-secondary/releases/26/Everything/sources/os"
    assert results[13].name == "pub/fedora/linux/development/27/Everything/x86_64/os"
    assert results[14].name == "pub/fedora/linux/releases/27/Everything/x86_64/os"

    # Run the script

    result = run_command(command_args)
    assert result.exit_code == 0
    assert (
        result.output == "pub/fedora/linux/development/27/Everything/x86_64/os => "
        "pub/fedora/linux/releases/27/Everything/x86_64/os\n"
    )
    # Ignore for now
    # assert stderr == ''

    # Check after running the script

    results = mirrormanager2.lib.get_repositories(db)
    assert len(results) == 2

    res = results[0]
    assert res.prefix == "fedora-27"
    assert res.name == "pub/fedora/linux/releases/27/Everything/x86_64/os"
    assert res.category.name == "Fedora Linux"
    assert res.version.name == "27"
    assert res.arch.name == "x86_64"
    assert res.directory.name == "pub/fedora/linux/releases/27/Everything/x86_64/os"

    res = results[1]
    assert res.prefix is None
    assert res.name == "pub/fedora/linux/releases/26/Everything/x86_64/os"
    assert res.category.name == "Fedora Linux"
    assert res.version.name == "26"
    assert res.arch.name == "x86_64"
    assert res.directory.name == "pub/fedora/linux/releases/26/Everything/x86_64/os"

    results = db.execute(sa.select(model.Directory)).scalars().all()
    # create_directory creates 9 directories
    # we create 6 more here, 9+6=15
    assert len(results) == 15
    assert results[9].name == "pub/fedora/linux/releases/26/Everything/x86_64/os"
    assert results[10].name == "pub/fedora/linux/releases/26/Everything/armhfp/os"
    assert results[11].name == "pub/fedora-secondary/releases/26/Everything/ppc64le/os"
    assert results[12].name == "pub/fedora-secondary/releases/26/Everything/sources/os"
    assert results[13].name == "pub/fedora/linux/development/27/Everything/x86_64/os"
    assert results[14].name == "pub/fedora/linux/releases/27/Everything/x86_64/os"

    # Check non-existing version

    args = command_args[:]
    args[2] = "--version=24"
    result = run_command(args)
    assert result.exit_code == 1
    assert result.output == "Error: Version 24 not found for product Fedora\n"
    # Ignore for now
    # assert stderr == ''

    # Check after running the script

    results = mirrormanager2.lib.get_repositories(db)
    assert len(results) == 2

    res = results[0]
    assert res.prefix == "fedora-27"
    assert res.name == "pub/fedora/linux/releases/27/Everything/x86_64/os"
    assert res.category.name == "Fedora Linux"
    assert res.version.name == "27"
    assert res.arch.name == "x86_64"
    assert res.directory.name == "pub/fedora/linux/releases/27/Everything/x86_64/os"

    res = results[1]
    assert res.prefix is None
    assert res.name == "pub/fedora/linux/releases/26/Everything/x86_64/os"
    assert res.category.name == "Fedora Linux"
    assert res.version.name == "26"
    assert res.arch.name == "x86_64"
    assert res.directory.name == "pub/fedora/linux/releases/26/Everything/x86_64/os"

    results = db.execute(sa.select(model.Directory)).scalars().all()
    # create_directory creates 9 directories
    # we create 6 more here, 9+6=15
    assert len(results) == 15
    assert results[9].name == "pub/fedora/linux/releases/26/Everything/x86_64/os"
    assert results[10].name == "pub/fedora/linux/releases/26/Everything/armhfp/os"
    assert results[11].name == "pub/fedora-secondary/releases/26/Everything/ppc64le/os"
    assert results[12].name == "pub/fedora-secondary/releases/26/Everything/sources/os"
    assert results[13].name == "pub/fedora/linux/development/27/Everything/x86_64/os"
    assert results[14].name == "pub/fedora/linux/releases/27/Everything/x86_64/os"
