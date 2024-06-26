# Copyright (C) 2008 by Alexander Koenig
# Copyright (C) 2008, 2015 by Adrian Reber
# Copyright (C) 2024 by Aurélien Bompard
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
# LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
# WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

import datetime
import gzip
import logging
import time
from collections import defaultdict
from contextlib import suppress

import click

from mirrormanager2.lib import read_config
from mirrormanager2.lib.database import get_db_manager
from mirrormanager2.lib.model import AccessStat, AccessStatCategory

from .common import config_option, setup_logging

logger = logging.getLogger(__name__)

# TODO: rich progress bar


@click.command()
@config_option
@click.option(
    "-o",
    "--offset",
    type=int,
    default=0,
    help=(
        "number of days which should be subtracted from today's date and be used as basis "
        "for log analysis"
    ),
)
@click.option("--debug", is_flag=True, default=False, help="enable debugging")
@click.argument(
    "logfile",
    type=click.Path(),
)
def main(config, logfile, offset, debug):
    config = read_config(config)
    db_manager = get_db_manager(config)
    setup_logging(debug)
    if not logfile.endswith(".gz"):
        logger.warning("Warning, the logfile must be gzipped")
    logger.info("Starting mirrorlist statistics parser")
    start = time.monotonic()
    date = datetime.date.today() - datetime.timedelta(days=offset)

    stats = parse_logfile(date, config, logfile)
    with db_manager.Session() as session:
        stats_store = StatsStore(session, date, stats["accesses"])
        stats_store.store("countries", stats["countries"])
        stats_store.store("archs", stats["archs"])
        stats_store.store("repositories", stats["repositories"])
        session.commit()

    logger.info(f"Mirrorlist statistics gathered in {int(time.monotonic() - start)}s")


def parse_logfile(date, config, logfile):
    accesses = 0
    countries = defaultdict(lambda: 0)
    repositories = defaultdict(lambda: 0)
    archs = defaultdict(lambda: 0)
    for line in gzip.open(logfile, "rt"):
        arguments = line.split()
        try:
            y, m, d = arguments[3][:10].split("-")
        except Exception:
            logger.exception(f"Could not read line {line!r}")
            continue
        if not ((int(y) == date.year) and (int(m) == date.month) and (int(d) == date.day)):
            continue
        country_code = arguments[5][:2]
        if country_code in config["EMBARGOED_COUNTRIES"]:
            countries["N/"] += 1
        else:
            countries[country_code] += 1
        with suppress(IndexError):
            arch = arguments[9].rstrip(";")
            archs[arch] += 1
        with suppress(IndexError):
            repo = arguments[7].rstrip(";")
            repositories[repo] += 1
        accesses += 1
    return {
        "countries": countries,
        "repositories": repositories,
        "archs": archs,
        "accesses": accesses,
    }


class StatsStore:
    def __init__(self, session, date, accesses):
        self.session = session
        self.date = date
        self.accesses = accesses

    def store(self, category_name, stats):
        category, _created = AccessStatCategory.get_or_create(name=category_name)
        for name, requests in stats.items():
            stat, _created = AccessStat.get_or_create(
                category_id=category.id, date=self.date, name=name
            )
            stat.requests = requests
            stat.percent = (float(requests) / float(self.accesses)) * 100
            self.session.add(stat)
        self.session.flush()
