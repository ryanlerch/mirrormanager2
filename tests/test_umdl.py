"""
mirrormanager2 tests for the `Update Master Directory List` (UMDL) cron.
"""

import logging
import os

import pytest
import sqlalchemy as sa
from click.testing import CliRunner

import mirrormanager2.lib
import mirrormanager2.lib.model as model
from mirrormanager2.utility import update_master_directory_list

FOLDER = os.path.dirname(os.path.abspath(__file__))


@pytest.fixture(autouse=True)
def reset_caches():
    update_master_directory_list.cname = "N/A"
    mirrormanager2.lib.umdl.arch_cache = None
    mirrormanager2.lib.umdl.version_cache = None


@pytest.fixture()
def configfile(tmp_path):
    path = tmp_path.joinpath("mirrormanager2_tests.cfg").as_posix()
    contents = f"""
SQLALCHEMY_DATABASE_URI = 'sqlite:///{tmp_path.as_posix()}/test.sqlite'
import os
DB_ALEMBIC_LOCATION = os.path.join("{FOLDER}", "..", "mirrormanager2", "lib", "migrations")
UMDL_PREFIX = '{FOLDER}/../testdata/'

# Specify whether the crawler should send a report by email
CRAWLER_SEND_EMAIL =  False

UMDL_MASTER_DIRECTORIES = [
    {{
        'type': 'directory',
        'path': '{FOLDER}/../testdata/pub/epel/',
        'category': 'Fedora EPEL'
    }},
    {{
        'type': 'directory',
        'path': '{FOLDER}/../testdata/pub/fedora/linux/',
        'category': 'Fedora Linux'
    }},
    {{
        'type': 'directory',
        'path': '{FOLDER}/../testdata/pub/fedora-secondary/',
        'category': 'Fedora Secondary Arches'
    }},
    {{
        'type': 'directory',
        'path': '{FOLDER}/../testdata/pub/archive/',
        'category': 'Fedora Archive'
    }},
    {{
        'type': 'directory',
        'path': '{FOLDER}/../testdata/pub/alt/',
        'category': 'Fedora Other'
    }}
]
    """
    with open(path, "w") as stream:
        stream.write(contents)
    return path


@pytest.fixture()
def command_args(configfile):
    return ["-c", configfile]


def run_command(args):
    runner = CliRunner()
    return runner.invoke(
        update_master_directory_list.main, args, env={"TERM": "dumb", "COLUMNS": "80"}
    )


def test_0_umdl_empty_db(command_args, db, caplog):
    """Test the umdl cron against an empty database."""
    caplog.set_level(logging.DEBUG)
    result = run_command(command_args)
    assert result.exit_code == 0, result.output

    # assert result.output == ""
    # Ignore for now
    # assert stderr == ''

    exp = [
        "Starting umdl",
        "UMDL_MASTER_DIRECTORIES Category Fedora EPEL does not exist in the database, skipping",
        "UMDL_MASTER_DIRECTORIES Category Fedora Linux does not exist in the database, skipping",
        (
            "UMDL_MASTER_DIRECTORIES Category Fedora Secondary Arches does not exist in the "
            "database, skipping"
        ),
        "UMDL_MASTER_DIRECTORIES Category Fedora Archive does not exist in the database, skipping",
        "UMDL_MASTER_DIRECTORIES Category Fedora Other does not exist in the database, skipping",
        "Ending umdl",
    ]
    assert caplog.messages == exp


def test_1_umdl(db, command_args, base_items, directory, category, categorydirectory, caplog):
    """Test the umdl cron."""
    caplog.set_level(logging.DEBUG)

    # Run the UDML
    result = run_command(command_args)
    assert result.exit_code == 0, result.output
    assert result.output == (
        "Syncing repositories of Fedora Linux ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100% " "0:00:00\n"
    )
    # Ignore for now
    # assert stderr == ''

    # The DB should now be filled with what UMDL added, so let's check it
    results = mirrormanager2.lib.get_versions(db)
    assert len(results) == 2
    for result in results:
        version_names = ["22", "20"]
        assert result.name in version_names
        if result.name == "22":
            assert result.product.name == "Fedora"
        if result.name == "20":
            assert result.product.name == "Fedora"

    results = mirrormanager2.lib.get_categories(db)
    assert len(results) == 3
    assert results[0].name == "Fedora Linux"
    assert results[1].name == "Fedora EPEL"
    assert results[2].name == "Fedora Codecs"

    results = mirrormanager2.lib.get_categories(db, True)
    assert len(results) == 2
    assert results[0].name == "Fedora Linux"
    assert results[1].name == "Fedora EPEL"

    results = mirrormanager2.lib.get_products(db)
    assert len(results) == 2
    assert results[0].name == "EPEL"
    assert results[1].name == "Fedora"

    results = mirrormanager2.lib.get_repositories(db)
    assert len(results) == 3
    check_counter = 0
    for result in results:
        if result.name == "pub/fedora/linux/development/22/x86_64/os":
            assert result.category.name == "Fedora Linux"
            assert result.version.name == "22"
            assert result.arch.name == "x86_64"
            assert result.directory.name == "pub/fedora/linux/development/22/x86_64/os"
            assert result.prefix is None
            check_counter += 1
        if result.name == "pub/fedora/linux/releases/20/Fedora/x86_64/os":
            assert result.category.name == "Fedora Linux"
            assert result.version.name == "20"
            assert result.arch.name == "x86_64"
            assert result.directory.name == "pub/fedora/linux/releases/20/Fedora/x86_64/os"
            assert result.prefix == "fedora-install-20"
            check_counter += 1

    assert check_counter == 2

    results = mirrormanager2.lib.get_arches(db)
    assert len(results) == 4
    assert results[0].name == "i386"
    assert results[1].name == "ppc"
    assert results[2].name == "source"
    assert results[3].name == "x86_64"

    results = db.execute(sa.select(model.Directory)).scalars().all()
    # tree testdata/pub says there are 49 directories and 49 files
    # There are 7 directories added by create_directory which are not
    # present on the FS, 49 + 7 = 56, so we are good \ó/
    assert len(results) == 56
    assert results[0].name == "pub/fedora/linux"
    assert results[1].name == "pub/fedora/linux/extras"
    assert results[2].name == "pub/epel"
    assert results[3].name == "pub/fedora/linux/releases/26"
    assert results[4].name == "pub/fedora/linux/releases/27"
    assert results[5].name == "pub/archive/fedora/linux/releases/26/Everything/source"
    assert results[20].name == "pub/fedora/linux/releases/20/Fedora/source/SRPMS/b"

    assert results[19].files["index.html"]["size"] == 6
    assert results[19].files["abattis-cantarell-fonts-0.0.15-1.fc20.src.rpm"]["size"] == 10
    assert results[19].files["abiword-3.0.0-4.fc20.src.rpm"]["size"] == 10
    assert results[19].files["aalib-1.4.0-0.23.rc5.fc20.src.rpm"]["size"] == 10

    results = mirrormanager2.lib.get_file_detail(db, "repomd.xml", 7)
    assert results is None

    results = db.execute(sa.select(model.FileDetail)).scalars().all()
    assert len(results) == 7, list([r.filename for r in results])

    expected = [
        {
            "filename": "repomd.xml",
            "directory": "pub/fedora/linux/development/22/x86_64/os/repodata",
            "md5": "d0fb87891c3bfbdaf7a225f57e9ba6ee",
            "sha512": (
                "7bb9a0bae076ccbbcd086163a1d4f33b62321aa6991d135c42bf3f6c42c4eb"
                "465a0b42c62efa809708543fcd69511cb19cd7111d5ff295a50253b9c7659bb9d6"
            ),
            "sha256": "860f0f832f7a641cf8f7e27172ef9b2492ce849388e43f372af7e512aa646677",
        },
        {
            "filename": "repomd.xml",
            "directory": "pub/fedora/linux/releases/20/Fedora/source/SRPMS/repodata",
            "md5": "082970dfa804fdcfaed2e15e2e5fba7d",
            "sha512": (
                "3351c7a6b1d2bd94e375d09324a9280b8becfe4dea40a227c3b270ddcedb19"
                "f420eec3f2c6a39a1edcdf52f80d31eb47a0ba25057ced2e3182dd212bc7466ba2"
            ),
            "sha256": "9a4738934092cf17e4540ee9cab741e922eb8306875ae5621feb01ebeb1f67f2",
        },
        {
            "filename": "Fedora-20-x86_64-DVD.iso",
            "directory": "pub/fedora/linux/releases/20/Fedora/x86_64/iso",
            "md5": None,
            "sha512": None,
            "sha256": "f2eeed5102b8890e9e6f4b9053717fe73031e699c4b76dc7028749ab66e7f917",
        },
        {
            "filename": "Fedora-20-x86_64-netinst.iso",
            "directory": "pub/fedora/linux/releases/20/Fedora/x86_64/iso",
            "md5": None,
            "sha512": None,
            "sha256": "376be7d4855ad6281cb139430606a782fd6189dcb01d7b61448e915802cc350f",
        },
        {
            "filename": "repomd.xml",
            "directory": "pub/fedora/linux/releases/20/Fedora/x86_64/os/repodata",
            "md5": "49db42c616518f465014c3605de4414d",
            "sha512": (
                "50ed8cb8f4daf8bcd1d0ccee1710b8a87ee8de5861fb15a1023d6558328795"
                "f42dade3e025c09c20ade36c77a3a82d9cdce1a2e2ad171f9974bc1889b5918020"
            ),
            "sha256": "108b4102829c0839c7712832577fe7da24f0a9491f4dc25d4145efe6aced2ebf",
        },
        {
            "filename": "Fedora-Live-Desktop-x86_64-20-1.iso",
            "directory": "pub/fedora/linux/releases/20/Live/x86_64",
            "md5": None,
            "sha512": None,
            "sha256": "cc0333be93c7ff2fb3148cb29360d2453f78913cc8aa6c6289ae6823372a77d2",
        },
        {
            "filename": "Fedora-Live-KDE-x86_64-20-1.iso",
            "directory": "pub/fedora/linux/releases/20/Live/x86_64",
            "md5": None,
            "sha512": None,
            "sha256": "08360a253b4a40dff948e568dba1d2ae9d931797f57aa08576b8b9f1ef7e4745",
        },
    ]

    assert expected == sorted(
        (
            {
                "filename": r.filename,
                "directory": r.directory.name,
                "md5": r.md5,
                "sha512": r.sha512,
                "sha256": r.sha256,
            }
            for r in results
        ),
        key=lambda item: item["directory"] + "/" + item["filename"],
    )

    results = db.execute(sa.select(model.HostCategoryDir)).scalars().all()
    assert len(results) == 0
